"""
essai_lecteur.py - T05 (RPi) : essai du lecteur de codes-barres USB.

1. Affiche les périphériques d'entrée (pour trouver le nom du lecteur).
2. Lit les billets scannés pendant 30 s et valide le format.

Usage : python3 essai_lecteur.py [partie_du_nom_du_lecteur]

Projet ESA - 243-557 - Automne 2026
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))   # racine prog/rpi
from modules.lecteur_code_barres import LecteurCodeBarres  # noqa: E402


def lecture(numero, texte):
    if numero is None:
        print(f"  Lu : '{texte}'  →  FORMAT INVALIDE")
    else:
        print(f"  Lu : '{texte}'  →  numéro {numero:06d} (à vérifier par T04)")


def main():
    print("Périphériques d'entrée :")
    for chemin, nom in LecteurCodeBarres.lister_peripheriques():
        print(f"  {chemin} : {nom}")

    nom = sys.argv[1] if len(sys.argv) > 1 else None
    lecteur = LecteurCodeBarres(rappel=lecture, nom_peripherique=nom)
    if not lecteur.demarrer():
        print("Lecteur non trouvé : relancer avec une partie de son nom en argument")
        return

    print("Lecteur prêt : scanner des billets (30 s)...")
    try:
        time.sleep(30)
    finally:
        lecteur.arreter()
    print("Fin de l'essai")


if __name__ == "__main__":
    main()