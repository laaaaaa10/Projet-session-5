#!/usr/bin/env python3
"""Raspberry Pi de la borne - Programme principal (integration RFID).

Lancement : sudo python3 prog/rpi/main.py
Options : --port /dev/ttyAMA0 --gpio 17 --chip 0 --delai-ms 500
"""

import sys
import time

from modules import gestion_comptes, lecteur_nfc_rfid


def traiter_badge(identifiant, comptes):
    """Cherche le compte d'une lecture valide et affiche son solde.

    Retourne le compte reconnu, ou None si le badge est inconnu.
    Cette etape ne debite rien et ne commande aucun actionneur.
    """
    numero = lecteur_nfc_rfid.numero_badge(identifiant)
    badge = f"Numero de badge : {numero} | ID UART : {identifiant}"
    compte = comptes.get(identifiant)
    if compte is None:
        print(f"BORNE | REFUSE | {badge} | Compte inconnu", flush=True)
        return None

    print(
        f"BORNE | COMPTE RECONNU | {compte.nom} | {badge}"
        f" | Solde : {compte.solde_affiche}",
        flush=True,
    )
    return compte


def main(argv=None):
    args = lecteur_nfc_rfid.lire_arguments(argv, description=__doc__)
    origine = time.monotonic()
    try:
        comptes = gestion_comptes.charger_comptes()
        print(f"BORNE | {len(comptes)} comptes charges.", flush=True)
        with lecteur_nfc_rfid.LecteurRFID(
            port=args.port, gpio=args.gpio, chip=args.chip, delai_ms=args.delai_ms,
        ) as lecteur:
            while True:
                for evenement in lecteur.lire():
                    print(f"[{time.monotonic() - origine:8.3f} s] {evenement}", flush=True)
                    if evenement.type == "ACCEPTE":
                        traiter_badge(evenement.identifiant, comptes)

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
