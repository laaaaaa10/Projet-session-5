"""T02 : consultation, credit et debit integral. Aucun calcul de tarif ici."""

from dataclasses import replace
from datetime import datetime, timezone

from modeles.comptes import (
    ConflitTransaction, ResultatOperation, StatutOperation, TypeOperation,
    valider_id_transaction, valider_id_uart, valider_montant,
)


class ServiceComptes:
    def __init__(self, depot):
        self.depot = depot

    def lister_comptes(self):
        with self.depot.transaction() as transaction:
            return dict(transaction.comptes)

    def consulter_compte(self, id_uart):
        id_uart = valider_id_uart(id_uart)
        return self.lister_comptes().get(id_uart)

    def retrouver_operation(self, id_transaction):
        valider_id_transaction(id_transaction)
        with self.depot.transaction() as transaction:
            return transaction.operations.get(id_transaction)

    def payer(self, id_transaction, id_uart, montant_centimes):
        return self._operer(TypeOperation.PAIEMENT, id_transaction, id_uart, montant_centimes)

    def crediter(self, id_transaction, id_uart, montant_centimes):
        return self._operer(TypeOperation.CREDIT, id_transaction, id_uart, montant_centimes)

    def _operer(self, type_operation, id_transaction, id_uart, montant):
        valider_id_transaction(id_transaction)
        id_uart = valider_id_uart(id_uart)
        valider_montant(montant, credit=type_operation == TypeOperation.CREDIT)
        with self.depot.transaction() as transaction:
            ancien = transaction.operations.get(id_transaction)
            if ancien is not None:
                if (ancien.type_operation, ancien.id_uart, ancien.montant_centimes) != (
                    type_operation, id_uart, montant,
                ):
                    raise ConflitTransaction("ID deja utilise avec d'autres donnees : " + id_transaction)
                return replace(ancien, deja_traitee=True)

            compte = transaction.comptes.get(id_uart)
            avant = apres = None
            if compte is None:
                statut = StatutOperation.COMPTE_INCONNU
            else:
                avant = apres = compte.solde_centimes
                if type_operation == TypeOperation.CREDIT:
                    statut, apres = StatutOperation.CREDITE, avant + montant
                elif avant >= montant:
                    statut, apres = StatutOperation.PAIE, avant - montant
                else:
                    statut = StatutOperation.SOLDE_INSUFFISANT
            resultat = ResultatOperation(
                id_transaction, datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                type_operation, id_uart, montant, statut, avant, apres,
            )
            transaction.enregistrer(resultat)
            return resultat
