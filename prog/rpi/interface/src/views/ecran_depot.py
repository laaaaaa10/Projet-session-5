"""
ecran_depot.py

 Created on: 25 nov. 2026
      Author: Javier Bolduc
"""

from interface.src.views.ecran_base import EcranBase


class EcranDepot(EcranBase):
    """Écran de dépôt : guide l'usager après le billet, pendant le rangement du véhicule (T11)."""

    def __init__(self):
        super().__init__("Dépôt du véhicule")

    def afficher(self):
        """Remet l'écran dans son état de départ."""
        self.texte.setText("Billet confirmé.\nAvancez votre véhicule sur la rampe.")

    def afficher_etat(self, message):
        """Met à jour l'état de l'opération en cours."""
        self.texte.setText(message)
