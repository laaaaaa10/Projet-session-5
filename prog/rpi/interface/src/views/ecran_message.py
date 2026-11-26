"""
ecran_message.py

 Created on: 25 nov. 2026
      Author: Javier Bolduc
"""

from interface.src.views.ecran_base import EcranBase


class EcranMessage(EcranBase):
    """Écran de message : erreurs, avertissements et confirmations."""

    def __init__(self):
        super().__init__("")
        self.bouton_ok = self.ajouter_bouton("OK")

    def afficher(self, titre, texte):
        self.titre.setText(titre)
        self.texte.setText(texte)
