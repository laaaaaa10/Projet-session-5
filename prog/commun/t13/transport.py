"""Transport Paho : callbacks courts, file bornee et reconnexion en arriere-plan."""

from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Lock
from uuid import uuid4

from .protocole import TAILLE_MAX, encoder
from .configuration import TOPICS_PI, TOPICS_PC

HORS_LIGNE = {"version": 1, "type": "disponibilite", "en_ligne": False}


@dataclass(frozen=True)
class MessageMQTT:
    topic: str
    payload: bytes
    retenu: bool = False


class TransportMQTT:
    def __init__(self, configuration, role):
        import paho.mqtt.client as mqtt
        if role not in {"pi", "pc"}:
            raise ValueError("Role MQTT invalide")
        self.config, self.role = configuration, role
        self._file = Queue(maxsize=256)
        self._verrou = Lock()
        self._connecte = False
        self._generation = 0
        self._incident = "Connexion non demarree"
        self.rejetes = 0
        self._demarre = False
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                   client_id=f"t13-{role}-{uuid4().hex}", clean_session=True)
        self._client.max_queued_messages_set(256)
        self._client.reconnect_delay_set(min_delay=1, max_delay=10)
        if configuration.utilisateur:
            self._client.username_pw_set(configuration.utilisateur, configuration.mot_de_passe)
        if configuration.tls:
            self._client.tls_set(ca_certs=configuration.certificat_ca)
        if role == "pi":
            self._client.will_set(configuration.topic("etat"),
                                  encoder(HORS_LIGNE), qos=1, retain=True)
        self._client.on_connect = self._connexion
        self._client.on_subscribe = self._abonne
        self._client.on_disconnect = self._deconnexion
        self._client.on_connect_fail = self._echec_connexion
        self._client.on_message = self._message

    @property
    def etat(self):
        with self._verrou:
            return self._connecte, self._generation, self._incident

    def _etat(self, connecte, incident=""):
        with self._verrou:
            self._connecte, self._incident = connecte, incident
            if connecte:
                self._generation += 1

    def _connexion(self, client, userdata, flags, raison, proprietes):
        if raison.is_failure:
            self._etat(False, f"Connexion refusee : {raison}")
            return
        noms = TOPICS_PC if self.role == "pi" else TOPICS_PI
        resultat, _ = client.subscribe([(self.config.topic(nom), 1) for nom in noms])
        if resultat != 0:
            self._etat(False, "Abonnement impossible")

    def _abonne(self, client, userdata, mid, raisons, proprietes):
        valide = bool(raisons) and all(not raison.is_failure for raison in raisons)
        self._etat(valide, "" if valide else "Abonnement refuse")

    def _deconnexion(self, client, userdata, flags, raison, proprietes):
        self._etat(False, f"MQTT deconnecte : {raison}")

    def _echec_connexion(self, client, userdata):
        self._etat(False, "Broker inaccessible ; nouvelle tentative automatique")

    def _message(self, client, userdata, message):
        if len(message.payload) > TAILLE_MAX:
            self.rejetes += 1
            return
        try:
            self._file.put_nowait(MessageMQTT(message.topic, bytes(message.payload), bool(message.retain)))
        except Full:
            self.rejetes += 1

    def demarrer(self):
        if self._demarre:
            return
        self._client.connect_async(self.config.hote, self.config.port, keepalive=10)
        self._client.loop_start()
        self._demarre = True

    def recevoir(self, maximum=8):
        messages = []
        for _ in range(maximum):
            try:
                messages.append(self._file.get_nowait())
            except Empty:
                break
        return messages

    def publier(self, nom, message, *, retenir=False):
        if not self.etat[0]:
            return False
        info = self._client.publish(self.config.topic(nom), encoder(message), qos=1, retain=retenir)
        return info.rc == 0  # Mise en file seulement, PAS une confirmation d'action.

    def fermer(self):
        if not self._demarre:
            return
        if self.role == "pi":
            self.publier("etat", HORS_LIGNE, retenir=True)
        self._client.disconnect()
        self._client.loop_stop()
        self._etat(False, "Client ferme")
        self._demarre = False
