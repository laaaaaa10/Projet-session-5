"""
raccordements.py

T01 - Points de branchement des tâches non livrées, appelés par les modules
déjà créés par T01 (même principe que application/integration_t04.py).

Chaque fonction appartient à la tâche indiquée. Elles ne prennent aucune
fausse décision : sans T04, aucune transaction n'est créée.

 Created on: 26 nov. 2026
      Author: Javier Bolduc
"""


def creer_transaction(numero_place, id_uart):
    """TODO(T04) : créer la transaction du dépôt (carte id_uart, place 1 à 14)
    et retourner son numéro (0 à 999 999). None = dépôt refusé."""
    return None


def conditions_confirmation():
    """TODO(T06/T13) : véhicule devant la barrière (IR d'entrée) et système en service.
    Retourne (permis, raison)."""
    return True, ""


def facturation(transaction_id, horodatage):
    """TODO(T04) : début de la facturation, appelé une seule fois par T11
    à la confirmation IR du dépôt."""
