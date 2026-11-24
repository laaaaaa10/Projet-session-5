#!/usr/bin/env python3
"""Demande de paiement de test T04 ; utilise le vrai lecteur RFID.

Arreter main.py avec Ctrl+C avant cet essai. Le montant fourni est debite
si le compte peut payer. --donnees permet de choisir un dossier d'essai.
Les options RFID --port, --gpio, --chip et --delai-ms restent disponibles.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.borne import Borne
from interface.console_borne import ConsoleBorne
from modeles.comptes import DemandePaiement
from modules.gestion_comptes import ServiceComptes
from modules import lecteur_nfc_rfid as rfid
from stockage.comptes_csv import DepotComptesCSV, DOSSIER_ACTIF


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id-transaction", required=True)
    parser.add_argument("--montant-centimes", type=int, required=True)
    parser.add_argument("--donnees", type=Path, default=DOSSIER_ACTIF)
    args, options_rfid = parser.parse_known_args(argv)
    materiel = rfid.lire_arguments(options_rfid)
    try:
        demande = DemandePaiement(args.id_transaction, args.montant_centimes)
        comptes = ServiceComptes(DepotComptesCSV(args.donnees))
        console = ConsoleBorne()
        console.demarrage(comptes.lister_comptes())
        borne = Borne(comptes, console)
        borne.demander_paiement(demande)
        # Un resultat deja enregistre est renvoye sans ouvrir UART/GPIO.
        resultats = borne.lire_resultats_paiement()
        if not resultats:
            with rfid.LecteurRFID(
                port=materiel.port, gpio=materiel.gpio, chip=materiel.chip,
                delai_ms=materiel.delai_ms,
            ) as lecteur:
                borne.executer(lecteur, un_paiement=True)
            resultats = borne.lire_resultats_paiement()
        return 0 if resultats[0].succes else 2
    except KeyboardInterrupt:
        print("\nEssai interrompu. Conserver le meme ID en cas de reprise.")
        return 130
    except Exception as erreur:
        print(f"ERREUR {type(erreur).__name__} : {erreur}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
