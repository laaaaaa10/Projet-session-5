"""
essai_pages_t05.py - T05 (RPi) : fenêtre d'essai des pages PageBillet et
PageSaisieBillet, en attendant la fenêtre principale de T01.

Usage : python3 essai_pages_t05.py            (bus CAN réel can0)
        python3 essai_pages_t05.py --simul    (STM32 Borne simulé, sans CAN)

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T05)
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "modules"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "interface"))

from PyQt6.QtCore import QTimer                                     # noqa: E402
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,  # noqa: E402
                             QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from billets import ID_IMPRESSION_ETAT, GestionBillets              # noqa: E402
from pages_billet import PageBillet, PageSaisieBillet               # noqa: E402

TRANSACTIONS_CONNUES = set()     # remplace T04 pour l'essai


def creer_envoi(simulation, billets_ref):
    """Retourne (fonction d'envoi, objet à arrêter)."""
    if simulation:
        def envoyer(identifiant, donnees):
            # STM32 simulé : répond 1 puis 2 sur la même séquence
            if identifiant == 0x361:
                seq = donnees[0]
                QTimer.singleShot(100, lambda: billets_ref[0].traiter_trame(
                    ID_IMPRESSION_ETAT, bytes([seq, 1, 0])))
                QTimer.singleShot(2000, lambda: billets_ref[0].traiter_trame(
                    ID_IMPRESSION_ETAT, bytes([seq, 2, 0])))
        return envoyer, None

    import can
    bus = can.Bus(interface="socketcan", channel="can0")

    def envoyer(identifiant, donnees):
        bus.send(can.Message(arbitration_id=identifiant, data=donnees,
                             is_extended_id=False))
    notifier = can.Notifier(bus, [lambda msg: billets_ref[0].traiter_trame(
        msg.arbitration_id, bytes(msg.data))])
    return envoyer, (notifier, bus)


def main():
    simulation = "--simul" in sys.argv
    app = QApplication(sys.argv)

    billets_ref = [None]
    envoyer, ressources = creer_envoi(simulation, billets_ref)
    billets = GestionBillets(envoyer)
    billets_ref[0] = billets

    page_billet = PageBillet(billets)
    page_saisie = PageSaisieBillet()
    pages = QStackedWidget()
    pages.addWidget(page_billet)
    pages.addWidget(page_saisie)

    # --- Simulation de la séquence de dépôt (T03/T04) --------------------
    def nouveau_depot():
        transaction = random.randint(0, 999_999)
        TRANSACTIONS_CONNUES.add(transaction)
        pages.setCurrentWidget(page_billet)
        page_billet.afficher_billet(transaction, random.randint(1, 14))

    page_billet.billet_confirme.connect(
        lambda t: print(f"[T03] billet {t:06d} confirmé : ouverture de la barrière autorisée"))

    # --- Simulation de T04 au retrait -------------------------------------
    def verifier(numero):
        print(f"[T04] vérification du numéro {numero:06d}")
        if numero in TRANSACTIONS_CONNUES:
            page_saisie.afficher_message(f"Transaction {numero:06d} trouvée", ok=True)
        else:
            page_saisie.afficher_message(f"Transaction {numero:06d} inconnue", ok=False)
        QTimer.singleShot(2500, page_saisie.reinitialiser)

    page_saisie.numero_saisi.connect(verifier)

    # --- Fenêtre d'essai (remplace la fenêtre principale de T01) ----------
    bouton_depot = QPushButton("Simuler un dépôt")
    bouton_retrait = QPushButton("Page retrait")
    bouton_depot.clicked.connect(nouveau_depot)
    bouton_retrait.clicked.connect(lambda: pages.setCurrentWidget(page_saisie))
    barre = QHBoxLayout()
    barre.addWidget(bouton_depot)
    barre.addWidget(bouton_retrait)

    centre = QWidget()
    disposition = QVBoxLayout(centre)
    disposition.addLayout(barre)
    disposition.addWidget(pages)

    fenetre = QMainWindow()
    fenetre.setWindowTitle("Essai T05 - " + ("simulation" if simulation else "bus CAN réel"))
    fenetre.setCentralWidget(centre)
    fenetre.resize(800, 480)
    fenetre.show()

    code = app.exec()
    if ressources:
        ressources[0].stop()
        ressources[1].shutdown()
    sys.exit(code)


if __name__ == "__main__":
    main()
