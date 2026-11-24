"""Acces public en lecture seule de T03 aux lectures RFID et aux soldes T02."""

from typing import Protocol, runtime_checkable

from modeles.comptes import ErreurStockage, IdentificationCarte

VERSION_INTERFACE = 1
__all__ = [
    "VERSION_INTERFACE", "IdentificationCarte", "InterfaceIdentification",
    "ModuleT03", "ErreurStockage",
]


@runtime_checkable
class InterfaceIdentification(Protocol):
    def lire_identifications(self) -> list[IdentificationCarte]:
        """Retire les nouvelles lectures valides, hors paiement T04."""
        ...

    def consulter_solde(self, id_uart: str) -> int | None:
        """Solde courant en centimes, ou None si compte inconnu. Ne modifie rien."""
        ...


class ModuleT03(Protocol):
    def actualiser(self) -> None:
        """Consomme les lectures disponibles puis rend la main rapidement."""
        ...
