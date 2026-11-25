"""
stationnement.py - Modèle partagé des 14 places (proposition, à valider en équipe).

Le RPi conserve, pour chaque place, deux informations DISTINCTES (énoncé ESA) :
  - l'état logique  : libre, réservé, occupé, maintenance, défaut
  - la présence physique mesurée par les capteurs IR (T06) : présent, absent, inconnu

T03 (réservation), T04 (transactions), T06 (IR), T07 (DEL), T11/T12 (séquences)
et T13 (supervision) lisent et modifient ce modèle ; il est protégé par un verrou
car la réception CAN se fait dans un autre fil.

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T03) - proposition de modèle commun
"""
import threading
from enum import Enum

NB_PLACES = 14
PLACES_PAR_ETAGE = 7


class EtatPlace(Enum):
    LIBRE = "libre"                # vert
    RESERVEE = "réservée"          # bleu
    OCCUPEE = "occupée"            # rouge
    MAINTENANCE = "maintenance"    # orange
    DEFAUT = "défaut"              # jaune clignotant


class Presence(Enum):
    ABSENT = "absent"
    PRESENT = "présent"
    INCONNU = "inconnu"            # capteur non fiable ou pas encore lu


def libelle_place(numero: int) -> str:
    """1..14 → 'E1.1'..'E2.7'."""
    if not 1 <= numero <= NB_PLACES:
        raise ValueError(f"place hors 1-{NB_PLACES} : {numero}")
    return f"E{1 + (numero - 1) // PLACES_PAR_ETAGE}.{1 + (numero - 1) % PLACES_PAR_ETAGE}"


def numero_place(libelle: str) -> int:
    """'E1.1'..'E2.7' → 1..14."""
    try:
        etage, rang = libelle.strip().upper().lstrip("E").split(".")
        etage, rang = int(etage), int(rang)
    except ValueError:
        raise ValueError(f"libellé de place invalide : {libelle!r}") from None
    if etage not in (1, 2) or not 1 <= rang <= PLACES_PAR_ETAGE:
        raise ValueError(f"libellé de place invalide : {libelle!r}")
    return (etage - 1) * PLACES_PAR_ETAGE + rang


class ModeleStationnement:
    """États logiques et présences physiques des 14 places (source de vérité du RPi)."""

    def __init__(self):
        self._verrou = threading.RLock()
        self._etats = {n: EtatPlace.LIBRE for n in range(1, NB_PLACES + 1)}
        self._presences = {n: Presence.INCONNU for n in range(1, NB_PLACES + 1)}

    @property
    def verrou(self):
        """Pour enchaîner plusieurs opérations de façon atomique (with modele.verrou:)."""
        return self._verrou

    def etat(self, numero: int) -> EtatPlace:
        with self._verrou:
            return self._etats[numero]

    def presence(self, numero: int) -> Presence:
        with self._verrou:
            return self._presences[numero]

    def changer_etat(self, numero: int, etat: EtatPlace) -> None:
        with self._verrou:
            self._etats[numero] = etat

    def changer_presence(self, numero: int, presence: Presence) -> None:
        """Appelée par T06 à la réception des trames IR."""
        with self._verrou:
            self._presences[numero] = presence

    def copie(self) -> dict:
        """{numéro: (état logique, présence physique)} - instantané pour l'affichage."""
        with self._verrou:
            return {n: (self._etats[n], self._presences[n]) for n in self._etats}
