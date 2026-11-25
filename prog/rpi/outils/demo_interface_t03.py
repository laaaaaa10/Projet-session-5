#!/usr/bin/env python3
"""Acces T03/T02 sur PC Linux, sans lecteur, reservation ni barriere.

Evenements RFID simules ; comptes et paiements reels dans un dossier temporaire.
"""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.paiements import DemandePaiement
from application.acces_identification import AccesIdentification
from application.borne import Borne
from exemples.client_t03 import ClientT03Exemple
from interface.console_borne import ConsoleBorne
from modules.gestion_comptes import ServiceComptes
from modules.lecteur_nfc_rfid import EvenementRFID
from stockage.comptes_csv import DepotComptesCSV


def main():
    with TemporaryDirectory(prefix="esa-t03-") as dossier:
        service = ServiceComptes(DepotComptesCSV(dossier))
        acces = AccesIdentification(service)
        borne = Borne(service, ConsoleBorne(), identification=acces)
        t03 = ClientT03Exemple(identification=acces)
        print("DEMO | Donnees temporaires ; aucun acces au lecteur.", flush=True)
        for id_uart in ("11008827F9", "1100823734", "1100880F2D"):
            borne.traiter_evenement(EvenementRFID("ACCEPTE", "evenement simule", id_uart))
            t03.actualiser()

        borne.demander_paiement(DemandePaiement("demo-separation", 500))
        borne.traiter_evenement(EvenementRFID("ACCEPTE", "paiement simule", "11008827F9"))
        print(f"DEMO | Lectures T03 pendant le paiement : {len(acces.lire_identifications())}")
        print(f"DEMO | Resultats T04 disponibles : {len(borne.lire_resultats_paiement())}")
        print(f"DEMO | Solde courant de Jason : {acces.consulter_solde('11008827F9')} centimes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
