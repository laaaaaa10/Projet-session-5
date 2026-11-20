#!/usr/bin/env python3
"""Raspberry Pi de la borne - Programme principal (integration RFID).

Lancement : sudo python3 prog/rpi/main.py
Options : --port /dev/ttyAMA0 --gpio 17 --chip 0 --delai-ms 500
"""

import sys
import time

from modules import lecteur_nfc_rfid


def traiter_badge(identifiant):
    """Point d'entree de la logique de borne pour une lecture acceptee.

    La validation du compte et la transaction seront ajoutees ici.
    Cet affichage ne donne aucune autorisation et ne commande aucun actionneur.
    """
    print(f"BORNE | Identifiant recu : {identifiant}", flush=True)


def main(argv=None):
    args = lecteur_nfc_rfid.lire_arguments(argv, description=__doc__)
    origine = time.monotonic()
    try:
        with lecteur_nfc_rfid.LecteurRFID(
            port=args.port, gpio=args.gpio, chip=args.chip, delai_ms=args.delai_ms,
        ) as lecteur:
            while True:
                for evenement in lecteur.lire():
                    print(f"[{time.monotonic() - origine:8.3f} s] {evenement}", flush=True)
                    if evenement.type == "ACCEPTE":
                        traiter_badge(evenement.identifiant)

                # TODO : ajouter ici les traitements non bloquants du CAN,
                # du MQTT, de l'ecran et des autres modules une fois initialises.
                # Ne pas attendre 500 ms ici : le module RFID gere ce delai.
                time.sleep(0.002)
    except KeyboardInterrupt:
        print("\nProgramme termine.")
        return 0
    except Exception as erreur:
        print(f"ERREUR {type(erreur).__name__} : {erreur}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
