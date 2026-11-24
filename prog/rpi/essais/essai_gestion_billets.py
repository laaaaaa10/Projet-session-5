"""
essai_gestion_billets.py - T05 (RPi) : essai de GestionBillets sur le bus réel.

Montre le fonctionnement non bloquant : la boucle principale continue de
tourner (compteur affiché) pendant que les réponses CAN arrivent.

Usage : python3 essai_gestion_billets.py [transaction] [place]

Projet ESA - 243-557 - Automne 2026
"""
import os
import sys
import time
from datetime import datetime

import can

# Permet d'importer prog/rpi/modules/billets.py depuis prog/rpi/essais/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "modules"))
from billets import GestionBillets  # noqa: E402


def main():
    transaction = int(sys.argv[1]) if len(sys.argv) > 1 else 4213
    place = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    bus = can.Bus(interface="socketcan", channel="can0")

    def envoyer(identifiant, donnees):
        bus.send(can.Message(arbitration_id=identifiant, data=donnees,
                             is_extended_id=False))

    billets = GestionBillets(envoyer)

    # Notifier : un fil séparé reçoit les trames et appelle notre fonction
    notifier = can.Notifier(bus, [lambda msg: billets.traiter_trame(
        msg.arbitration_id, bytes(msg.data))])

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
    notifier.stop()
    bus.shutdown()


if __name__ == "__main__":
    main()