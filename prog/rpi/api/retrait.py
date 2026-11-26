"""Contrat proposé T12/T04 : préparation financière, sans CAN, GPIO ou CSV.

T04 est propriétaire du tarif, du délai, des tentatives T02 et de leur
persistance. T12 reçoit des instantanés ; il ne consomme pas la file T02.
Les temps monotones sont locaux au processus, jamais restaurés après reboot.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from modeles.comptes import ResultatOperation, valider_id_transaction

DELAI_PAIEMENT_S = 60.0


def valider_id_retrait(valeur):
    valider_id_transaction(valeur)
    return valeur


@dataclass(frozen=True)
class TransactionRetrait:
    numero: int
    place: int

    def __post_init__(self):
        if type(self.numero) is not int or not 0 <= self.numero <= 999_999:
            raise ValueError("Numéro de transaction attendu : entier 0 à 999999")
        if type(self.place) is not int or not 1 <= self.place <= 14:
            raise ValueError("Place attendue : entier 1 à 14")


class StatutRetrait(str, Enum):
    ATTENTE = "ATTENTE"
    PAYE = "PAYE"
    EXPIRE = "EXPIRE"
    ANNULE = "ANNULE"
    INCERTAIN = "INCERTAIN"


@dataclass(frozen=True)
class FenetreRetrait:
    id_retrait: str
    transaction: TransactionRetrait
    montant_centimes: int
    ouverte_a: float
    expire_a: float


@dataclass(frozen=True)
class SuiviRetrait:
    fenetre: FenetreRetrait
    statut: StatutRetrait
    paiement: ResultatOperation | None = None
    valide_a: float | None = None
    message: str = ""


class RetraitRefuse(ValueError):
    """Refus certain de T04 : inconnu, déjà payé, ou autre retrait en cours."""


class InterfaceFacturationRetrait(Protocol):
    def identifier_transaction(self, transaction_id: int) -> TransactionRetrait | None:
        """Lecture seule ; ne fige rien et ne déclenche aucun paiement."""
        ...

    def figer_montant(self, transaction_id: int, id_retrait: str) -> SuiviRetrait:
        """Persister l'intention avant T02. Même ID : même montant et échéance.

        Un autre ID ne peut ouvrir un second paiement pour une transaction
        déjà payée. Une nouvelle demande après expiration recalcule depuis
        le dépôt initial. Aucun cumul des soldes de cartes n'est permis.
        """
        ...

    def consulter_retrait(self, id_retrait: str) -> SuiviRetrait:
        """Instantané corrélé, incluant l'expiration. Ne retire aucun événement.

        PAYE exige un reçu T02 PAIE intégral, une seule carte, et une validation
        dans [ouverte_a, expire_a[. Une erreur technique reste INCERTAIN.
        """
        ...

    def annuler_retrait(self, id_retrait: str) -> SuiviRetrait:
        """Annuler l'attente, puis réconcilier le reçu durable T02.

        Si le paiement était déjà validé, retourner PAYE sans remboursement.
        Même ID : aucun nouvel effet. Ne clôture jamais le stationnement.
        """
        ...
