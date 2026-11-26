"""
ecran_tactile.py

Interface - Écran tactile (Magedok T007-2, 7 po, relié au Raspberry Pi 5
par HDMI pour la vidéo et USB pour le tactile).

T01 : fenêtre principale de la borne. Elle contient les écrans de T01 et
les pages des autres tâches (T03, T05), gère la navigation entre eux et
crée une seule fois les objets partagés (bus CAN, pont T02, modules).

Lancement (depuis la racine du dépôt) :
    python3 -B prog/rpi/interface/ecran_tactile.py                (Pi : can0, lecteur RFID)
    python3 -B prog/rpi/interface/ecran_tactile.py --simulation   (PC : aucun matériel)
Options du lecteur RFID : --port --gpio --chip --delai-ms (comme main.py).

Branchement des autres tâches : voir src/hardware/evenements.py (crochets
et signaux) et src/hardware/raccordements.py (T04, T06, T13).

 Created on: 25 nov. 2026
      Author: Javier Bolduc
"""

import sys
from pathlib import Path

if __package__ in (None, ""):          # lancement direct : racine prog/rpi
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import Qt                                                   # noqa: E402
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget         # noqa: E402

from interface.qt.pages_billet import PageBillet, PageSaisieBillet           # noqa: E402
from interface.qt.pages_reservation import (PageCarte, PageConfirmationDepot,  # noqa: E402
                                             PageReservation)
from interface.src.config import HAUTEUR_ECRAN, LARGEUR_ECRAN, PLEIN_ECRAN   # noqa: E402
from interface.src.controllers.controleur_interface import ControleurInterface  # noqa: E402
from interface.src.hardware.evenements import EvenementsBorne                # noqa: E402
from interface.src.hardware.services import Services                         # noqa: E402
from interface.src.views.cadre_page import CadrePage                         # noqa: E402
from interface.src.views.ecran_accueil import EcranAccueil                   # noqa: E402
from interface.src.views.ecran_depot import EcranDepot                       # noqa: E402
from interface.src.views.ecran_message import EcranMessage                   # noqa: E402
from interface.src.views.ecran_recuperation import EcranRecuperation         # noqa: E402
from modules.lecteur_nfc_rfid import lire_arguments                          # noqa: E402


class EcranTactile(QMainWindow):
    """Fenêtre principale : contient les écrans et gère la navigation entre eux."""

    def __init__(self, services):
        super().__init__()
        self.services = services
        self.setWindowTitle("Borne ESA")
        self._fermeture_demandee = False

        # Écrans de T01
        self.ecran_accueil = EcranAccueil()
        self.ecran_depot = EcranDepot()
        self.ecran_recuperation = EcranRecuperation()
        self.ecran_message = EcranMessage()

        # Pages des autres tâches
        self.page_carte = PageCarte()                                      # T03
        self.page_reservation = PageReservation(services.reservation)      # T03
        self.page_confirmation = PageConfirmationDepot(services.reservation)  # T03
        self.page_billet = PageBillet(services.billets)                    # T05
        self.page_saisie_billet = PageSaisieBillet()                       # T05

        # Pages sans bouton de retour : T01 ajoute « Annuler » dessous
        self.cadre_reservation = CadrePage(self.page_reservation)
        self.cadre_saisie_billet = CadrePage(self.page_saisie_billet)

        self.ecrans = {
            "accueil": self.ecran_accueil,
            "carte": self.page_carte,
            "reservation": self.cadre_reservation,
            "confirmation": self.page_confirmation,
            "billet": self.page_billet,
            "depot": self.ecran_depot,
            "saisie_billet": self.cadre_saisie_billet,
            "recuperation": self.ecran_recuperation,
            "message": self.ecran_message,
        }
        self.pile = QStackedWidget()
        for ecran in self.ecrans.values():
            self.pile.addWidget(ecran)
        self.setCentralWidget(self.pile)

        self.evenements = EvenementsBorne()
        self.controleur = ControleurInterface(self, services, self.evenements)

    def afficher_ecran(self, nom):
        """Affiche l'écran demandé (une clé de self.ecrans)."""
        self.pile.setCurrentWidget(self.ecrans[nom])

    def ecran_courant(self):
        """Nom de l'écran affiché."""
        return next(nom for nom, ecran in self.ecrans.items() if ecran is self.pile.currentWidget())

    def demarrer(self, plein_ecran=PLEIN_ECRAN):
        """Ouvre la fenêtre."""
        if plein_ecran:
            QApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
            self.showFullScreen()
        else:
            self.setFixedSize(LARGEUR_ECRAN, HAUTEUR_ECRAN)
            self.show()

    def arreter(self):
        """Ferme la fenêtre."""
        self.close()

    def closeEvent(self, evenement):
        """T02 : la fenêtre attend la fermeture du lecteur (signal arrete) avant de fermer."""
        pont = self.services.pont_t02
        if pont.en_cours:
            evenement.ignore()
            if not self._fermeture_demandee:
                self._fermeture_demandee = True
                pont.arrete.connect(self.close)
                pont.arreter()
            return
        super().closeEvent(evenement)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    simulation = "--simulation" in argv
    args = lire_arguments([a for a in argv if a != "--simulation"], description=__doc__)

    app = QApplication(sys.argv)
    services = Services(simulation, options_lecteur={
        "port": args.port, "gpio": args.gpio, "chip": args.chip, "delai_ms": args.delai_ms,
    })
    ecran = EcranTactile(services)
    services.demarrer()
    ecran.demarrer(plein_ecran=PLEIN_ECRAN and not simulation)
    code = app.exec()
    services.arreter()
    return code


if __name__ == "__main__":
    sys.exit(main())
