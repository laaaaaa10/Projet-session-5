#!/usr/bin/env python3
"""Banc MQTT/T02 sans lecteur ni CAN. --donnees est obligatoire et explicite."""

import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.acces_comptes import AccesComptes
from commun.t13.configuration import ConfigurationMQTT
from commun.t13.transport import TransportMQTT
from modules.gestion_comptes import ServiceComptes
from modules.supervision import SupervisionT13
from stockage.comptes_csv import DepotComptesCSV


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donnees", required=True, type=Path)
    parser.add_argument("--simuler-service", action="store_true",
                        help="Activer explicitement le banc T03/T11/T12 et securite CAN simules")
    args = parser.parse_args(argv)
    config = ConfigurationMQTT.depuis_environnement()
    transport = TransportMQTT(config, "pi")
    service = None
    if args.simuler_service:
        from exemples.systeme_t13_simule import SystemeT13Simule
        from modules.service_t13 import GestionServiceT13
        service = GestionServiceT13(
            SystemeT13Simule(args.donnees / "scenario-service.json"),
            args.donnees / "service-simule.sqlite3",
            cible=f"simulation:{config.hote}:{config.port}/{config.prefixe}",
        )
        print("SIMULATION SERVICE ACTIVE : aucun GPIO/CAN/moteur ; utiliser un dossier d'essai.", flush=True)
    module = SupervisionT13(AccesComptes(ServiceComptes(DepotComptesCSV(args.donnees))), transport,
                           service=service)
    print(f"Banc T13 | vrais comptes T02 dans {args.donnees.resolve()} | lecteur/CAN absents", flush=True)
    transport.demarrer()
    try:
        while True:
            module.actualiser()
            time.sleep(0.02)
    except KeyboardInterrupt:
        return 0
    finally:
        module.fermer()


if __name__ == "__main__":
    raise SystemExit(main())
