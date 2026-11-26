"""Exclusion T11/T12 portée par le ServiceCAN partagé, jamais par MQTT.

Un défaut conserve le propriétaire. Un acquittement explicite libère le verrou,
mais ne lance rien. Avec T12, les séquences CAN ne sont pas réutilisées dans un processus :
le protocole n'a pas d'identifiant d'époque permettant de reconnaître un vieux
résultat après bouclage. L'épuisement exige une intervention, sans recyclage.
"""
import threading

_CREATION = threading.Lock()


class ArbitreMecanique:
    def __init__(self, *, sequences_sans_reemploi=False):
        self._verrou = threading.RLock()
        self.proprietaire = None
        self.bloque = False
        self.raison = ""
        self.nouvelles_autorisees = True  # compatibilité T11 seul ; T13 impose son état
        self._sequence = 0
        self._utilisations = 0
        self.sequences_sans_reemploi = sequences_sans_reemploi

    def prendre(self, proprietaire, *, deja_confirmee=False):
        with self._verrou:
            if self.bloque or (not self.nouvelles_autorisees and not deja_confirmee):
                return False
            if self.proprietaire is not None:
                return self.proprietaire is proprietaire
            self.proprietaire = proprietaire
            return True

    def liberer(self, proprietaire):
        with self._verrou:
            if self.bloque or self.proprietaire is not proprietaire:
                return False
            self.proprietaire = None
            return True

    def verrouiller(self, raison):
        with self._verrou:
            self.bloque, self.raison = True, raison

    def acquitter(self, proprietaire):
        """Réservé à une intervention validée ; ne réinitialise pas les séquences."""
        with self._verrou:
            if self.proprietaire not in (None, proprietaire):
                return False
            self.bloque, self.raison, self.proprietaire = False, "", None
            return True

    def envoyer(self, proprietaire, can, identifiant, donnees):
        """L'arrêt et l'émission sont sérialisés : pas d'ordre lancé après verrouillage."""
        with self._verrou:
            if self.bloque or self.proprietaire is not proprietaire:
                raise RuntimeError("Émission interdite par l'arbitre mécanique")
            can.envoyer(identifiant, donnees)

    def sequence(self):
        with self._verrou:
            if self.sequences_sans_reemploi and self._utilisations >= 254:
                raise RuntimeError("Séquences CAN épuisées : intervention requise, aucun bouclage")
            self._utilisations += 1
            self._sequence = (self._sequence + 1) % 255
            return self._sequence


def arbitre_du_can(can):
    """Un seul arbitre, même pour les doubles de ServiceCAN utilisés en test."""
    with _CREATION:
        if not hasattr(can, "arbitre_mecanique"):
            can.arbitre_mecanique = ArbitreMecanique()
        return can.arbitre_mecanique
