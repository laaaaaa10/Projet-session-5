"""Acces local T13 -> T02 : consultation et credit, sans transport MQTT."""

from typing import Protocol, runtime_checkable

from modeles.comptes import ConflitTransaction, ErreurStockage, ResultatOperation, StatutOperation

VERSION_INTERFACE = 1
__all__ = [
    "VERSION_INTERFACE", "InterfaceComptes", "ModuleT13", "ResultatOperation",
    "StatutOperation", "ConflitTransaction", "ErreurStockage",
]


@runtime_checkable
class InterfaceComptes(Protocol):
    def consulter_solde(self, id_uart: str) -> int | None:
        """Solde courant en centimes, ou None si compte inconnu."""
        ...

    def lister_soldes(self) -> dict[str, int]:
        """Instantane des soldes par ID UART complet, pour la synchronisation."""
        ...

    def ajouter_credit(self, id_transaction: str, id_uart: str,
                       montant_centimes: int) -> ResultatOperation:
        """Credit integral et journalise ; conserver le meme ID lors des repetitions."""
        ...

    def retrouver_resultat_credit(self, id_transaction: str) -> ResultatOperation | None:
        """Resultat durable d'un credit, ou None ; rejette l'ID d'un paiement."""
        ...


class ModuleT13(Protocol):
    def actualiser(self) -> None:
        """Traite les commandes et reponses disponibles, sans attendre le reseau."""
        ...
