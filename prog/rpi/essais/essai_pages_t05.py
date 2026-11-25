"""
essai_pages_t05.py - T05 (RPi) : fenêtre d'essai des pages PageBillet et
PageSaisieBillet, en attendant la fenêtre principale de T01.

Usage : python3 essai_pages_t05.py            (bus CAN réel can0)
        python3 essai_pages_t05.py --simul    (STM32 Borne simulé, bus virtuel)

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T05)
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))   # racine prog/rpi

from PyQt6.QtCore import QTimer                                       # noqa: E402
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,  # noqa: E402
                             QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from communications.can_bus import ServiceCAN                         # noqa: E402
from interface.qt.pages_billet import PageBillet, PageSaisieBillet    # noqa: E402
from modules.billets import creer_gestion_billets                     # noqa: E402

TRANSACTIONS_CONNUES = set()     # remplace T04 pour l'essai


def main():
    simulation = "--simul" in sys.argv
    app = QApplication(sys.argv)

    simulateur = None
    if simulation:
        from exemples.simulateur_stm32_borne import SimulateurStm32Borne
        service = ServiceCAN(interface="virtual", channel="esa")
        simulateur = SimulateurStm32Borne(channel="esa")
        simulateur.demarrer()
    else:
        service = ServiceCAN()
    billets = creer_gestion_billets(service)
    try:
        service.demarrer()
    except Exception as erreur:
        print(f"Bus CAN indisponible ({erreur}) : les impressions échoueront")

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
    service.arreter()
    if simulateur:
        simulateur.arreter()
    sys.exit(code)


if __name__ == "__main__":
    main()
