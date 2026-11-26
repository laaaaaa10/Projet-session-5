"""
ecran_accueil.py

 Created on: 25 nov. 2026
      Author: Javier Bolduc
"""

from interface.src.views.ecran_base import EcranBase


class EcranAccueil(EcranBase):
    """Écran d'attente : message d'accueil quand aucun usager n'est présent."""

    def __init__(self):
        super().__init__("Bienvenue")
        self.bouton_depot = self.ajouter_bouton("Déposer un véhicule")
        self.bouton_retrait = self.ajouter_bouton("Récupérer un véhicule")

    def afficher(self):
        """Remet l'écran dans son état de départ (borne en service)."""
        self.titre.setText("Bienvenue")
        self.texte.setText("Choisissez une opération.")
        self._activer_boutons(True)

    def afficher_presence(self, present):
        """Change le message selon le radar."""
        if present:
            self.texte.setText("Bonjour ! Choisissez une opération.")
        else:
            self.texte.setText("Approchez-vous de la borne.")

    def afficher_hors_service(self, raison):
        """Borne indisponible : les boutons sont désactivés."""
        self.titre.setText("Hors service")
        self.texte.setText(raison or "La borne est temporairement hors service.")
        self._activer_boutons(False)

    def _activer_boutons(self, actif):
        self.bouton_depot.setEnabled(actif)
        self.bouton_retrait.setEnabled(actif)
