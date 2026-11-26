"""
session.py

T01 - Opération en cours pour l'usager devant la borne.

 Created on: 25 nov. 2026
      Author: Javier Bolduc
"""

from dataclasses import dataclass

OPERATION_DEPOT = "depot"
OPERATION_RETRAIT = "retrait"


@dataclass
class Session:
    operation: str | None = None    # OPERATION_DEPOT, OPERATION_RETRAIT ou None
    id_session: str | None = None   # session de réservation T03 (dépôt)
    id_uart: str | None = None      # carte acceptée (dépôt)
    transaction_id: int | None = None
    place: int | None = None        # 1 à 14
    numero: int | None = None       # numéro de billet saisi (retrait), en attente de T04
    id_paiement: str | None = None  # demande de paiement T04 affichée (retrait)
    id_retrait: str | None = None   # ID stable T12, distinct de chaque tentative T02
    en_cours: bool = False          # transaction créée ou payée : plus d'annulation

    def commencer(self, operation, id_session=None):
        """Démarre une nouvelle opération."""
        self.reinitialiser()
        self.operation = operation
        self.id_session = id_session

    def reinitialiser(self):
        """Aucune opération en cours."""
        self.operation = self.id_session = self.id_uart = None
        self.transaction_id = self.place = self.numero = self.id_paiement = None
        self.id_retrait = None
        self.en_cours = False
