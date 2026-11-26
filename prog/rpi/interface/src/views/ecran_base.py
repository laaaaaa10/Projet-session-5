"""
ecran_base.py

T01 - Mise en page commune aux écrans de T01 : un titre, un texte et une
rangée de boutons. Le style ne s'applique qu'à ces écrans, pas aux pages
des autres tâches.

 Created on: 25 nov. 2026
      Author: Javier Bolduc
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

STYLE = """
QWidget { font-size: 26px; }
QLabel#titre { font-size: 40px; font-weight: bold; }
QPushButton { min-height: 90px; font-size: 28px; }
"""


class EcranBase(QWidget):

    def __init__(self, titre):
        super().__init__()
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)

        self.titre = QLabel(titre)
        self.titre.setObjectName("titre")
        self.titre.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.texte = QLabel()
        self.texte.setWordWrap(True)
        self.texte.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.zone_boutons = QHBoxLayout()

        layout.addWidget(self.titre)
        layout.addWidget(self.texte, 1)
        layout.addLayout(self.zone_boutons)

    def ajouter_bouton(self, texte):
        """Ajoute un bouton en bas de l'écran et le retourne."""
        bouton = QPushButton(texte)
        self.zone_boutons.addWidget(bouton)
        return bouton
