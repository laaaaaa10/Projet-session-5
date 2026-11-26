"""Supervision T13 : acces T02 et gestion de service optionnelle explicite."""

from dataclasses import asdict
import time
from uuid import uuid4

from api.comptes import ConflitTransaction, ErreurStockage
from commun.t13.protocole import (
    ACTIONS_SERVICE, canal_commande, canal_reponse, decoder, id_valide,
    repartir_etat, reponse, valider_commande,
)

class SupervisionT13:
    def __init__(self, comptes, transport, *, horloge=time.monotonic, periode=5.0, service=None):
        self.comptes, self.transport = comptes, transport
        self.service = service
        self.horloge, self.periode = horloge, periode
        self._session = uuid4().hex
        self._revision = 0
        self._generation = 0
        self._publication = float("-inf")
        self.messages_invalides = 0

    def instantane(self):
        """Pas de faux etat LIBRE, EN_SERVICE ou absence d'anomalie."""
        self._revision += 1
        anomalies = [{"code": "MODULES_NON_RACCORDES", "message":
                      "T03/T04/T06/T11/T12 reels non raccordes" if self.service else
                      "T03/T04/T06/T11/T12 et gestion de service non raccordes"}]
        try:
            soldes = self.comptes.lister_soldes()
        except ErreurStockage:
            soldes = None
            anomalies.append({"code": "STOCKAGE_T02", "message": "Soldes indisponibles"})
        etat = {
            "version": 1, "session": self._session, "revision": self._revision,
            "source": "PI", "en_ligne": True, "etat_service": "INCONNU", "arret_verrouille": None,
            "soldes": soldes,
            "places": [{"id": f"E{niveau}.{place}", "logique": "INCONNU", "presence": None}
                       for niveau in (1, 2) for place in range(1, 8)],
            "transactions": None, "statistiques": None, "anomalies": anomalies,
            "disponibilite": {"T02": soldes is not None, "T03": False, "T04": False,
                              "T06": False, "T11": False, "T12": False, "service": self.service is not None},
        }
        if self.service is not None:
            etat.update(self.service.instantane())
            if etat["service_simule"]:
                anomalies.append({"code": "SIMULATION_SERVICE", "message":
                                  "SIMULATION T03/T11/T12 et securite CAN : aucun moteur commande"})
            if etat["arret_verrouille"]:
                anomalies.append({"code": "ARRET_VERROUILLE", "message":
                                  "Arret verrouille : intervention et reinitialisation requises"})
            if etat["incident_service"]:
                anomalies.append({"code": etat["incident_service"], "message": etat["incident_service"]})
        return etat

    def _publier_resultats_service(self, resultats):
        for resultat in resultats:
            self.transport.publier("commande/reponse", resultat)
            self._publication = float("-inf")

    def _repondre(self, demande, phase, code, donnees=None):
        self.transport.publier(canal_reponse(demande["commande"]), reponse(demande, phase, code, donnees))

    def _traiter(self, message):
        if message.topic not in {self.transport.config.topic("commande"), self.transport.config.topic("comptes/commande")}:
            return
        demande = None
        try:
            demande = decoder(message.payload)
            valider_commande(demande)
            if message.topic != self.transport.config.topic(canal_commande(demande["commande"])):
                raise ValueError("Commande recue sur le mauvais topic")
            if message.retenu:
                raise ValueError("Commande retenue interdite")
        except ValueError as erreur:
            self.messages_invalides += 1
            if (demande and id_valide(demande.get("id_commande"))
                    and isinstance(demande.get("commande"), str) and len(demande["commande"]) <= 128):
                self._repondre(demande, "REFUSEE", "MESSAGE_INVALIDE", {"message": str(erreur)})
            return
        action, params = demande["commande"], demande["parametres"]
        if action in ACTIONS_SERVICE:
            if self.service is None:
                self._repondre(demande, "REFUSEE", "MODULE_INDISPONIBLE",
                               {"message": "Gestion de service/CAN non raccordee ; aucune action executee"})
            else:
                self._publier_resultats_service(self.service.traiter(demande))
            return
        self._repondre(demande, "ACCEPTEE", "DEMANDE_VALIDEE")
        try:
            if action == "SYNCHRONISER":
                self._repondre(demande, "TERMINEE", "SYNCHRONISE", {"etat": self.instantane()})
            elif action == "CONSULTER_SOLDE":
                solde = self.comptes.consulter_solde(params["id_uart"])
                self._repondre(demande, "TERMINEE", "COMPTE_INCONNU" if solde is None else "SOLDE",
                               {"id_uart": params["id_uart"], "solde_centimes": solde})
            elif action == "AJOUTER_CREDIT":
                # Cet ID vient du PC et a ete conserve AVANT le premier envoi.
                resultat = self.comptes.ajouter_credit(demande["id_commande"], **params)
                recu = asdict(resultat)
                recu["statut"] = resultat.statut.value
                recu["type_operation"] = resultat.type_operation.value
                self._repondre(demande, "TERMINEE", resultat.statut.value, {"recu": recu})
                self._publication = float("-inf")  # Solde actuel dans un instantane distinct.
        except ConflitTransaction:
            self._repondre(demande, "REFUSEE", "CONFLIT_TRANSACTION")
        except ValueError as erreur:
            self._repondre(demande, "REFUSEE", "PARAMETRES_INVALIDES", {"message": str(erreur)})
        except ErreurStockage:
            # L'operation peut deja etre dans le journal. Jamais un faux refus/succes.
            self._repondre(demande, "INCERTAINE", "ERREUR_STOCKAGE",
                           {"message": "Reprendre exactement la meme demande et le meme ID"})

    def actualiser(self):
        # La progression locale ne depend jamais du Wi-Fi ni du broker.
        if self.service is not None:
            self._publier_resultats_service(self.service.actualiser())
        connecte, generation, _ = self.transport.etat
        if not connecte:
            return
        if generation != self._generation:
            self._generation = generation
            self._publication = float("-inf")
        # Le callback ne touche jamais aux comptes. Travail borne a huit messages.
        for message in self.transport.recevoir(maximum=8):
            self._traiter(message)
        if self.horloge() - self._publication >= self.periode:
            for nom, contenu in repartir_etat(self.instantane()).items():
                self.transport.publier(nom, contenu, retenir=True)
            self._publication = self.horloge()

    def fermer(self):
        try:
            self.transport.fermer()
        finally:
            if self.service is not None:
                self.service.fermer()
