#!/usr/bin/env python3
"""Borne Raspberry Pi : assemblage des modules et liberation du materiel.

Lancement : sudo python3 prog/rpi/main.py
Options : --port /dev/ttyAMA0 --gpio 17 --chip 0 --delai-ms 500
Un badge seul consulte le compte. T04 doit demander un paiement explicitement.
"""

import sys

from application.borne import Borne
from application.acces_identification import AccesIdentification
from application.acces_comptes import AccesComptes
from application import integration_t03, integration_t04, integration_t13
from interface.console_borne import ConsoleBorne
from modules.gestion_comptes import ServiceComptes
from modules import lecteur_nfc_rfid
from stockage.comptes_csv import DepotComptesCSV, DOSSIER_ACTIF


def main(argv=None, *, dossier_donnees=DOSSIER_ACTIF):
    args = lecteur_nfc_rfid.lire_arguments(argv, description=__doc__)
    try:
        comptes = ServiceComptes(DepotComptesCSV(dossier_donnees))
        console = ConsoleBorne()
        console.demarrage(comptes.lister_comptes())
        identification = AccesIdentification(comptes)
        t03 = integration_t03.creer_module_t03(identification)
        borne = Borne(
            comptes, console, identification=identification if t03 is not None else None,
        )
        t04 = integration_t04.creer_module_t04(borne)
        t13 = integration_t13.creer_module_t13(AccesComptes(comptes))
        with lecteur_nfc_rfid.LecteurRFID(
            port=args.port, gpio=args.gpio, chip=args.chip, delai_ms=args.delai_ms,
        ) as lecteur:
            borne.executer(lecteur, t03=t03, t04=t04, t13=t13)
    except KeyboardInterrupt:
        print("\nProgramme termine.")
        return 0
    except Exception as erreur:
        print(f"ERREUR {type(erreur).__name__} : {erreur}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
