"""Exemple pour le responsable T04 : aucune connaissance de RFID ou des CSV.

Le montant est fourni par l'appelant, sans calcul de tarif ici. Ce client
illustre le contrat ; il n'est pas active dans le programme de la borne.
"""

from api.paiements import DemandePaiement, InterfacePaiement, ResultatOperation, StatutOperation


class ClientT04Exemple:
    def __init__(self, paiements: InterfacePaiement):
        self.paiements = paiements
        self.resultats: dict[str, ResultatOperation] = {}

    def payer_facture(self, id_transaction: str, montant_centimes: int) -> None:
        """T04 fournit un ID stable pour cette tentative, meme en cas de reprise."""
        self.paiements.demander_paiement(DemandePaiement(id_transaction, montant_centimes))

    def actualiser(self) -> None:
        """Appelee par la boucle commune ; aucune attente de carte ni sleep ici."""
        for resultat in self.paiements.lire_resultats_paiement():
            if resultat.id_transaction in self.resultats:
                continue  # Une notification repetee ne repete pas les effets T04.
            self.resultats[resultat.id_transaction] = resultat
            if resultat.statut == StatutOperation.PAIE:
                print(f"T04 EXEMPLE | {resultat.id_transaction} | Facture payee", flush=True)
            else:
                print(f"T04 EXEMPLE | {resultat.id_transaction} | Refus : {resultat.statut.value}",
                      flush=True)
        # Dans le vrai T04, enregistrer durablement le resultat et l'etat de la
        # facture. Le dictionnaire ci-dessus deduplique seulement dans ce processus.
