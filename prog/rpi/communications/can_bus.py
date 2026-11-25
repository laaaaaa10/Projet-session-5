"""
can_bus.py - Service CAN commun du Raspberry Pi (proposition partagée).

Un seul objet ServiceCAN ouvre can0 pour toute l'application. Chaque module
(T05, T06, T11, T12...) s'abonne aux identifiants qui le concernent et envoie
ses trames par le même service : aucune tâche n'ouvre son propre bus.

  service = ServiceCAN()                       # can0 réel
  service = ServiceCAN(interface="virtual")    # essais sans matériel
  service.abonner([0x230], rappel)             # rappel(identifiant, donnees)
  service.demarrer()
  service.envoyer(0x360, donnees)

ATTENTION : les rappels sont appelés dans le fil de réception de python-can,
pas dans le fil Qt. Ils doivent être courts et protégés par un verrou, ou
transmettre l'information à l'interface par un signal Qt.

Protocole CAN ESA v1.6 : trames de données standard (11 bits), DLC 0 à 8.
Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T05) - proposition de service commun
"""
import logging
import threading

JOURNAL = logging.getLogger(__name__)


class ServiceCAN:
    """Accès unique au bus CAN : envoi et distribution des trames reçues."""

    def __init__(self, interface="socketcan", channel="can0", **options):
        self._interface = interface
        self._channel = channel
        self._options = options
        self._bus = None
        self._notifier = None
        self._abonnements = []            # [(ensemble d'identifiants ou None, rappel)]
        self._verrou = threading.Lock()

    # ------------------------------------------------------------- cycle de vie
    def demarrer(self) -> None:
        """Ouvre le bus et lance la réception en arrière-plan.
        Lève can.CanError (ou OSError) si can0 n'est pas actif."""
        import can                         # importé ici : les tests sans CAN restent possibles
        if self._bus is not None:
            return
        self._bus = can.Bus(interface=self._interface, channel=self._channel, **self._options)
        self._notifier = can.Notifier(self._bus, [self._distribuer])

    def arreter(self) -> None:
        if self._notifier is not None:
            self._notifier.stop()
            self._notifier = None
        if self._bus is not None:
            self._bus.shutdown()
            self._bus = None

    @property
    def actif(self) -> bool:
        return self._bus is not None

    # ------------------------------------------------------------------- envoi
    def envoyer(self, identifiant: int, donnees: bytes) -> None:
        """Envoie une trame de données standard. Lève une exception si impossible."""
        import can
        if self._bus is None:
            raise RuntimeError("bus CAN non démarré")
        if not 0 <= identifiant <= 0x7FF or len(donnees) > 8:
            raise ValueError(f"trame invalide : ID 0x{identifiant:X}, {len(donnees)} octets")
        self._bus.send(can.Message(arbitration_id=identifiant, data=bytes(donnees),
                                   is_extended_id=False))

    # --------------------------------------------------------------- réception
    def abonner(self, identifiants, rappel) -> None:
        """rappel(identifiant, donnees) pour chaque trame dont l'ID est dans
        identifiants (liste) ; identifiants = None pour recevoir toutes les trames."""
        ensemble = None if identifiants is None else frozenset(identifiants)
        with self._verrou:
            self._abonnements.append((ensemble, rappel))

    def _distribuer(self, message) -> None:
        if message.is_extended_id or message.is_remote_frame or message.is_error_frame:
            return                          # protocole ESA : trames de données standard
        identifiant, donnees = message.arbitration_id, bytes(message.data)
        with self._verrou:
            abonnements = list(self._abonnements)
        for ensemble, rappel in abonnements:
            if ensemble is None or identifiant in ensemble:
                try:
                    rappel(identifiant, donnees)
                except Exception:           # un module défaillant ne bloque pas les autres
                    JOURNAL.exception("Erreur dans un rappel CAN (ID 0x%03X)", identifiant)
