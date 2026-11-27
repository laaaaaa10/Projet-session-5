"""Contrats T12 : observations de sécurité et clôture appartenant à T04.

Aucun booléen par défaut ne certifie une position ou une barrière. Le producteur
réel des observations reste à raccorder ; le banc fournit un double identifié.
"""
from dataclasses import dataclass
from typing import Protocol

from api.retrait import TransactionRetrait, valider_id_retrait


@dataclass(frozen=True)
class ConditionsRetrait:
    observe_a: float
    barriere_fermee: bool = False
    defauts_leves: bool = False
    parcours_valide: bool = False
    bras_retracte_sur: bool = False
    reference_verticale: bool = False
    reference_angulaire: bool = False
    intervention_confirmee: bool = False


class InterfaceSecuriteRetrait(Protocol):
    def conditions(self) -> ConditionsRetrait: ...


@dataclass(frozen=True)
class SortieCloturee:
    id_retrait: str
    transaction_id: int
    place: int

    def __post_init__(self):
        valider_id_retrait(self.id_retrait)
        TransactionRetrait(self.transaction_id, self.place)


class InterfaceSortieRetrait(Protocol):
    def cloturer_sortie(self, id_retrait: str, transaction_id: int, place: int) -> SortieCloturee:
        """T04 persiste la sortie et libère ses ressources logiques UNE seule fois.

        Même ID : même reçu, sans nouveau débit ni nouvelle clôture. T12 appelle
        seulement après les IR présence puis absence et la fin de mécanique.
        """
        ...

    def consulter_sortie(self, id_retrait: str) -> SortieCloturee | None:
        """Lecture seule pour réconciliation explicite après une réponse perdue."""
        ...
