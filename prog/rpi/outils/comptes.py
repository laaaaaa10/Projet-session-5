#!/usr/bin/env python3
"""Consulter ou crediter les comptes locaux ; aucune creation de compte."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from interface.console_borne import ConsoleBorne
from modules.gestion_comptes import ServiceComptes
from stockage.comptes_csv import DepotComptesCSV, DOSSIER_ACTIF


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donnees", type=Path, default=DOSSIER_ACTIF)
    commandes = parser.add_subparsers(dest="commande", required=True)
    commandes.add_parser("consulter", help="afficher les deux comptes")
    credit = commandes.add_parser("crediter", help="ajouter un montant avec une reference unique")
    credit.add_argument("--id-transaction", required=True)
    credit.add_argument("--id-uart", required=True)
    credit.add_argument("--montant-centimes", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        service = ServiceComptes(DepotComptesCSV(args.donnees))
        console = ConsoleBorne()
        if args.commande == "consulter":
            for compte in service.lister_comptes().values():
                console.compte(compte.id_uart, compte)
            return 0
        resultat = service.crediter(args.id_transaction, args.id_uart, args.montant_centimes)
        console.resultat_paiement(resultat)
        return 0 if resultat.succes else 2
    except Exception as erreur:
        print(f"ERREUR {type(erreur).__name__} : {erreur}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
