"""Adaptateur de T02 pour les consultations et credits provenant de T13."""

from dataclasses import replace

from modeles.comptes import ConflitTransaction, ResultatOperation, TypeOperation
from modules.gestion_comptes import ServiceComptes


class AccesComptes:
    def __init__(self, comptes: ServiceComptes):
        self._comptes = comptes

    def consulter_solde(self, id_uart: str) -> int | None:
        compte = self._comptes.consulter_compte(id_uart)
        return None if compte is None else compte.solde_centimes

    def lister_soldes(self) -> dict[str, int]:
        return {id_uart: compte.solde_centimes
                for id_uart, compte in self._comptes.lister_comptes().items()}

    def ajouter_credit(self, id_transaction: str, id_uart: str,
                       montant_centimes: int) -> ResultatOperation:
        return self._comptes.crediter(id_transaction, id_uart, montant_centimes)

    def retrouver_resultat_credit(self, id_transaction: str) -> ResultatOperation | None:
        resultat = self._comptes.retrouver_operation(id_transaction)
        if resultat is None:
            return None
        if resultat.type_operation != TypeOperation.CREDIT:
            raise ConflitTransaction("Cet ID designe un paiement, pas un credit")
        return replace(resultat, deja_traitee=True)
