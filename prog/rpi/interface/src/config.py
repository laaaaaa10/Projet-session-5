"""
config.py

T01 - Configuration de la fenêtre principale de l'écran tactile.

 Created on: 25 nov. 2026
      Author: Javier Bolduc
"""

# Résolution native du Magedok T007-2
LARGEUR_ECRAN = 1024
HAUTEUR_ECRAN = 600

# Plein écran et curseur caché sur le Raspberry Pi (ignoré avec --simulation)
PLEIN_ECRAN = True

# Délais (secondes)
DELAI_INACTIVITE_S = 30       # retour à l'accueil si l'usager n'agit plus
DELAI_MESSAGE_S = 8           # durée d'affichage d'un message de fin
DELAI_REFUS_BILLET_S = 2.5    # message « transaction inconnue » avant une nouvelle saisie
DELAI_OPERATION_S = 300       # sécurité : rangement / récupération sans fin annoncée

# Période de mise à jour des modules (T11) et du suivi de l'opération
PERIODE_SUIVI_MS = 100
