"""Contrat propose T13 -> adaptateur T03/T11/T12/securite CAN.

Le seul adaptateur fourni pour ce jalon est une simulation. Les futurs
adaptateurs reels doivent obtenir leurs confirmations des modules proprietaires.
Toutes les methodes sont non bloquantes et appelees dans le thread de T13.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ConditionsService:
    transaction: str = "AUCUNE"  # AUCUNE, NON_CONFIRMEE, CONFIRMEE
    rampe_occupee: bool = False
    defauts_leves: bool = False
    intervention_confirmee: bool = False
    bras_retracte_sur: bool = False
    reference_verticale: bool = False
    reference_angulaire: bool = False

    def obstacles(self, *, intervention=False):
        controles = {
            "DEFAUT_ACTIF": self.defauts_leves,
            "BRAS_NON_SUR": self.bras_retracte_sur,
            "REFERENCE_VERTICALE_INVALIDE": self.reference_verticale,
            "REFERENCE_ANGULAIRE_INVALIDE": self.reference_angulaire,
        }
        if intervention:
            controles["INTERVENTION_NON_CONFIRMEE"] = self.intervention_confirmee
        return [code for code, pret in controles.items() if not pret]


class InterfaceServiceT13(Protocol):
    simulation: bool

    def actualiser(self) -> None: ...
    def conditions(self) -> ConditionsService: ...
    def autoriser_nouvelles(self, autoriser: bool) -> None: ...
    def annuler_non_confirmee(self) -> None: ...
    def arreter(self) -> None: ...
    def lancer_rearmement(self, identifiant: str) -> None: ...
    def resultat_rearmement(self, identifiant: str) -> bool | None: ...
    def diagnostic(self) -> dict: ...
