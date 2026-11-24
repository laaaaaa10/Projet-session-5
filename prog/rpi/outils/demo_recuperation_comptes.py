#!/usr/bin/env python3
"""Illustre une recuperation du CSV des soldes, exclusivement sur fichiers temporaires.

Simule l'etat apres journal confirme mais avant mise a jour des soldes :
le journal contient le paiement, tandis que comptes.csv contient encore 20 $.
"""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.gestion_comptes import ServiceComptes
from stockage.comptes_csv import DepotComptesCSV


def main():
    with TemporaryDirectory(prefix="esa-reprise-") as dossier:
        depot = DepotComptesCSV(dossier)
        service = ServiceComptes(depot)
        service.lister_comptes()
        ancien_csv = depot.comptes.read_bytes()
        service.payer("demo-reprise", "11008827F9", 500)
        # UNIQUEMENT dans ce dossier temporaire : reproduire un instantane en retard.
        depot.comptes.write_bytes(ancien_csv)
        print("DEMO | CSV a 2000 centimes, journal confirmant un paiement de 500.", flush=True)
        print("DEMO | Relecture du meme paiement : recuperation attendue sur stderr.", flush=True)
        service = ServiceComptes(DepotComptesCSV(dossier))
        resultat = service.payer("demo-reprise", "11008827F9", 500)
        print(f"DEMO | Reprise : deja_traitee={resultat.deja_traitee}", flush=True)
        print(f"DEMO | Solde final : {service.consulter_compte('11008827F9').solde_centimes} centimes",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
