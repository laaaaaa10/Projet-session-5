#!/usr/bin/env python3
"""Acces comptes T13/T02 sur PC Linux, sans MQTT ni lecteur.

Tous les mouvements sont dans un dossier temporaire supprime a la fin.
"""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.comptes import ConflitTransaction
from application.acces_comptes import AccesComptes
from modules.gestion_comptes import ServiceComptes
from stockage.comptes_csv import DepotComptesCSV


def main():
    with TemporaryDirectory(prefix="esa-t13-") as dossier:
        acces = AccesComptes(ServiceComptes(DepotComptesCSV(dossier)))
        print("DEMO | Donnees temporaires ; aucun acces MQTT ou lecteur.", flush=True)
        print(f"DEMO | Solde initial de Jason : {acces.consulter_solde('11008827F9')} centimes")
        for _ in range(2):
            resultat = acces.ajouter_credit("t13:credit-001", "11008827F9", 500)
            print(f"DEMO | {resultat.statut.value} | Solde apres credit :"
                  f" {resultat.solde_apres_centimes} centimes | deja_traitee={resultat.deja_traitee}")
        try:
            acces.ajouter_credit("t13:credit-001", "11008827F9", 600)
        except ConflitTransaction:
            print("DEMO | CONFLIT_TRANSACTION | Meme ID avec un autre montant : refuse")
        inconnu = acces.ajouter_credit("t13:credit-002", "1100880F2D", 500)
        print(f"DEMO | Carte inconnue : {inconnu.statut.value}")
        acces = AccesComptes(ServiceComptes(DepotComptesCSV(dossier)))
        resultat = acces.retrouver_resultat_credit("t13:credit-001")
        print(f"DEMO | Reprise : deja_traitee={resultat.deja_traitee}")
        for id_uart, solde in acces.lister_soldes().items():
            print(f"DEMO | Solde courant : {id_uart} | {solde} centimes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
