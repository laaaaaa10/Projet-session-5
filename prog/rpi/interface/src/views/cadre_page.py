"""
cadre_page.py

T01 - Ajoute un bouton « Annuler » sous une page d'une autre tâche qui n'en a
pas (PageReservation, PageSaisieBillet), sans modifier cette page.

 Created on: 26 nov. 2026
      Author: Javier Bolduc
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton


class CadrePage(QWidget):

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.bouton_annuler = QPushButton("Annuler")
        self.bouton_annuler.setStyleSheet("font-size: 22px; min-height: 56px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page, 1)
        layout.addWidget(self.bouton_annuler)
