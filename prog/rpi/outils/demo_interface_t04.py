#!/usr/bin/env python3
"""Demonstration de l'API T04/T02 sur PC Linux, sans carte ni GPIO.

Les evenements RFID sont simules ; les modules de paiement/stockage sont reels.
Tous les mouvements sont dans un dossier temporaire supprime a la fin.
"""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.borne import Borne
from exemples.client_t04 import ClientT04Exemple
from interface.console_borne import ConsoleBorne
from modules.gestion_comptes import ServiceComptes
from modules.lecteur_nfc_rfid import EvenementRFID
from stockage.comptes_csv import DepotComptesCSV


def main():
    with TemporaryDirectory(prefix="esa-t04-") as dossier:
        service = ServiceComptes(DepotComptesCSV(dossier))
        borne = Borne(service, ConsoleBorne())
        t04 = ClientT04Exemple(paiements=borne)
        print("DEMO | Donnees temporaires ; aucun acces au lecteur.", flush=True)
        for reference, montant, id_uart in (
            ("demo-paiement", 550, "11008827F9"),
            ("demo-solde-insuffisant", 2500, "1100823734"),
            ("demo-carte-inconnue", 500, "1100880F2D"),
        ):
            t04.payer_facture(reference, montant)
            borne.traiter_evenement(EvenementRFID("ACCEPTE", "evenement simule", id_uart))
            t04.actualiser()

        # Meme demande apres reconstruction de la borne : resultat immediat,
        # sans nouvel evenement RFID et sans nouveau debit.
        borne = Borne(ServiceComptes(DepotComptesCSV(dossier)), ConsoleBorne())
        t04 = ClientT04Exemple(paiements=borne)
        t04.payer_facture("demo-paiement", 550)
        t04.actualiser()
        resultat = borne.retrouver_resultat_paiement("demo-paiement")
        print(f"DEMO | Reprise : deja_traitee={resultat.deja_traitee}", flush=True)
        for compte in service.lister_comptes().values():
            print(f"DEMO | {compte.nom} | Solde final : {compte.solde_affiche}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
