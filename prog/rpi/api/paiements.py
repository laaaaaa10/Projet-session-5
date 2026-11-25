"""API publique T04/T02, version 1. Aucun acces au materiel ni aux fichiers.

T04 recoit un objet InterfacePaiement ; il ne le construit pas. La borne
existante implemente ce contrat. Voir INTERFACE_T04_T02.md et exemples/client_t04.py.
"""

from typing import Protocol, runtime_checkable

from modeles.comptes import (
    ConflitTransaction, DemandePaiement, ErreurStockage, PaiementEnCours,
    ResultatOperation, StatutOperation,
)

VERSION_INTERFACE = 1
__all__ = [
    "VERSION_INTERFACE", "InterfacePaiement", "ModuleT04", "DemandePaiement",
    "ResultatOperation", "StatutOperation", "ConflitTransaction",
    "PaiementEnCours", "ErreurStockage",
]


@runtime_checkable
class InterfacePaiement(Protocol):
    """Contrat implemente par Borne, injectable dans le module de facturation."""

    def demander_paiement(self, demande: DemandePaiement) -> None:
        """Ouvre une attente de badge ou remet en file un resultat deja connu."""
        ...

    def lire_resultats_paiement(self) -> list[ResultatOperation]:
        """Vide la file de resultats ; a appeler regulierement par T04 uniquement."""
        ...

    def retrouver_resultat_paiement(self, id_transaction: str) -> ResultatOperation | None:
        """Relit un resultat durable sans vider la file. None = aucun resultat connu."""
        ...

    def annuler_paiement(self, id_transaction: str) -> bool:
        """Annule une attente non terminee ; ne rembourse jamais un paiement."""
        ...


class ModuleT04(Protocol):
    """Seul point d'entree periodique attendu du futur module de facturation."""

    def actualiser(self) -> None:
        """Traite les demandes/resultats disponibles, puis rend la main rapidement."""
        ...
