"""
ecran_recuperation.py

 Created on: 25 nov. 2026
      Author: Javier Bolduc
"""

from interface.src.views.ecran_base import EcranBase
from modeles.comptes import afficher_montant


class EcranRecuperation(EcranBase):
    """Écran de récupération : paiement (T04 / T02), puis récupération du véhicule (T12)."""

    def __init__(self):
        super().__init__("Récupération du véhicule")
        self.bouton_confirmer = self.ajouter_bouton("Confirmer le retrait")
        self.bouton_confirmer.hide()
        self.bouton_annuler = self.ajouter_bouton("Annuler")

    def afficher(self):
        """Remet l'écran dans son état de départ (billet trouvé par T04)."""
        self.texte.setText("Billet trouvé.\nConfirmez pour ouvrir le paiement de 60 secondes.")
        self.bouton_confirmer.show()
        self.bouton_confirmer.setEnabled(True)
        self.bouton_annuler.setEnabled(True)

    def afficher_paiement(self, montant_centimes):
        """Demande de paiement reçue du pont T02."""
        self.bouton_confirmer.hide()
        self.texte.setText(f"Montant à payer : {afficher_montant(montant_centimes)}\n"
                           "Présentez votre carte devant le lecteur.")

    def afficher_etat(self, message):
        """Met à jour l'état de l'opération en cours."""
        self.bouton_confirmer.hide()
        self.texte.setText(message)
