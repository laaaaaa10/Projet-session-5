"""
essai_gestion_billets.py - T05 (RPi) : essai de GestionBillets sur le bus réel.

Montre le fonctionnement non bloquant : la boucle principale continue de
tourner (compteur affiché) pendant que les réponses CAN arrivent.
Utilise le service CAN commun (communications/can_bus.py).

Usage : python3 essai_gestion_billets.py [transaction] [place] [--simul]

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T05)
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))   # racine prog/rpi
from communications.can_bus import ServiceCAN  # noqa: E402
from modules.billets import creer_gestion_billets  # noqa: E402


def main():
    arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
    simulation = "--simul" in sys.argv
    transaction = int(arguments[0]) if len(arguments) > 0 else 4213
    place = int(arguments[1]) if len(arguments) > 1 else 3

    simulateur = None
    if simulation:
        from exemples.simulateur_stm32_borne import SimulateurStm32Borne
        service = ServiceCAN(interface="virtual", channel="esa")
        simulateur = SimulateurStm32Borne(channel="esa")
        simulateur.demarrer()
    else:
        service = ServiceCAN()               # can0
    billets = creer_gestion_billets(service)
    service.demarrer()

    sequence = billets.demander_impression(transaction, place, datetime.now())
    print(f"Demande envoyée (séquence {sequence}) - la boucle continue sans attendre")

    dernier = None
    for tour in range(60):                     # 60 x 100 ms = 6 s max
        billets.mettre_a_jour()
        etat = billets.obtenir_etat(sequence)
        if etat != dernier:
            print(f"  tour {tour:2d} : {etat}")
            dernier = etat
        if billets.etat_brut(sequence).est_finale:
            break
        time.sleep(0.1)                        # simule le reste de l'application

    print(f"Numéro de transaction : {transaction:06d}")
    service.arreter()
    if simulateur:
        simulateur.arreter()


if __name__ == "__main__":
    main()
