"""
ecran_tactile.py

Interface - Écran tactile (Magedok T007-2, 7 po, relié au Raspberry Pi 5
par HDMI pour la vidéo et USB pour le tactile).

 Created on: 18 nov. 2026
      Author: Jonathan Marois
"""

# TODO : choisir la bibliothèque graphique (PyQt6 est utilisé dans le lit de clous)
#        et ajouter les imports nécessaires.


class EcranTactile:
    """Fenêtre principale : contient les écrans et gère la navigation entre eux."""

    def afficher_ecran(self, nom):
        """Affiche l'écran demandé."""
        pass

    def demarrer(self):
        """Ouvre la fenêtre."""
        pass

    def arreter(self):
        """Ferme la fenêtre."""
        pass


class EcranAccueil:
    """Écran d'attente : message d'accueil quand aucun usager n'est présent."""

    def afficher(self):
        pass


class EcranIdentification:
    """Écran d'identification : demande à l'usager de présenter sa carte (NFC-RFID)."""

    def afficher(self):
        pass

    def afficher_resultat(self, identifie):
        """Indique si la carte a été acceptée ou refusée."""
        pass


class EcranDepot:
    """Écran de dépôt : guide l'usager pendant le dépôt et le rangement du véhicule."""

    def afficher(self):
        pass

    def afficher_etat(self, message):
        """Met à jour l'état de l'opération en cours."""
        pass


class EcranRecuperation:
    """Écran de récupération : demande le code-barres du reçu pour récupérer le véhicule."""

    def afficher(self):
        pass

    def afficher_etat(self, message):
        """Met à jour l'état de l'opération en cours."""
        pass


class EcranMessage:
    """Écran de message : erreurs, avertissements et confirmations."""

    def afficher(self, titre, texte):
        pass
