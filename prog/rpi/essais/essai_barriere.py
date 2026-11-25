"""
essai_barriere.py - T03 (RPi) : essai et calibration du servo de la barrière.

Commandes au clavier :
  o = ouvrir     f = fermer     q = quitter
  nombre (ex. 1500) = impulsion en µs, pour trouver les positions à calibrer

Usage : python3 essai_barriere.py [--simul]

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T03)
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))   # racine prog/rpi
from modules import barriere  # noqa: E402
from modules.barriere import CommandeBarriere  # noqa: E402


def main():
    simulation = "--simul" in sys.argv
    commande = CommandeBarriere(simulation=simulation)
    print("Barrière prête" + (" (simulation)" if simulation else "")
          + f" - fermée = {barriere.IMPULSION_FERMEE_US} µs, "
            f"ouverte = {barriere.IMPULSION_OUVERTE_US} µs")
    try:
        while True:
            choix = input("o / f / µs / q > ").strip().lower()
            if choix == "q":
                break
            if choix == "o":
                commande.ouvrir()
            elif choix == "f":
                commande.fermer()
            elif choix.isdigit() and not simulation:
                commande._pwm.regler_impulsion(barriere.CANAL_SERVO, int(choix))
                print(f"  impulsion {choix} µs")
                continue
            else:
                continue
            print(f"  état : {commande.etat().value}")
            time.sleep(barriere.TEMPS_MOUVEMENT_S + 0.05)
            print(f"  état : {commande.etat().value}  (est_ouverte = {commande.est_ouverte()})")
    finally:
        commande.liberer()


if __name__ == "__main__":
    main()
