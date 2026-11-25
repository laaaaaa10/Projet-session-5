"""Affichage console ; aucune decision de paiement dans cette classe."""

import time

from modeles.comptes import afficher_montant
from modules.lecteur_nfc_rfid import numero_badge


class ConsoleBorne:
    def __init__(self):
        self.origine = time.monotonic()

    def demarrage(self, comptes):
        print(f"BORNE | {len(comptes)} comptes charges.", flush=True)

    def evenement_rfid(self, evenement):
        print(f"[{time.monotonic() - self.origine:8.3f} s] {evenement}", flush=True)

    def compte(self, id_uart, compte):
        badge = f"Numero de badge : {numero_badge(id_uart)} | ID UART : {id_uart}"
        if compte is None:
            print(f"BORNE | REFUSE | {badge} | Compte inconnu", flush=True)
        else:
            print(f"BORNE | COMPTE RECONNU | {compte.nom} | {badge}"
                  f" | Solde : {compte.solde_affiche}", flush=True)

    def attente_paiement(self, demande):
        print(f"BORNE | PAIEMENT EN ATTENTE | Transaction : {demande.id_transaction}"
              f" | Montant T04 : {afficher_montant(demande.montant_centimes)}"
              " | Presentez un badge.", flush=True)

    def resultat_paiement(self, resultat):
        detail = ""
        if resultat.solde_apres_centimes is not None:
            detail += f" | Solde apres operation : {afficher_montant(resultat.solde_apres_centimes)}"
        if resultat.deja_traitee:
            detail += " | Resultat deja enregistre, aucun nouveau mouvement"
        print(f"BORNE | {resultat.statut.value} | Transaction : {resultat.id_transaction}"
              f" | ID UART : {resultat.id_uart}"
              f" | Montant : {afficher_montant(resultat.montant_centimes)}{detail}", flush=True)

    def annulation(self, id_transaction):
        print(f"BORNE | ATTENTE ANNULEE | Transaction : {id_transaction}", flush=True)
