"""Contrat de paiement T04 -> T02, sans dependance au materiel ou au stockage."""

from dataclasses import dataclass
from enum import Enum
import re


def valider_id_uart(valeur):
    if not isinstance(valeur, str) or re.fullmatch(r"[0-9A-Fa-f]{10}", valeur) is None:
        raise ValueError("ID UART attendu : exactement 10 caracteres hexadecimaux")
    return valeur.upper()


def valider_id_transaction(valeur):
    if not isinstance(valeur, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", valeur) is None:
        raise ValueError("ID de transaction attendu : 1 a 128 caracteres (lettres, chiffres, _ . : -)")
    return valeur


def valider_montant(valeur, *, credit=False):
    # bool est un sous-type de int : True ne doit pas devenir un paiement de 1 cent.
    if type(valeur) is not int or valeur < (1 if credit else 0):
        raise ValueError("Montant attendu en centimes entiers " +
                         ("strictement positifs" if credit else "positifs ou nuls"))
    return valeur


def afficher_montant(centimes):
    dollars, cents = divmod(centimes, 100)
    return f"{dollars},{cents:02d} $"


@dataclass(frozen=True)
class Compte:
    id_uart: str
    nom: str
    solde_centimes: int

    @property
    def solde_affiche(self):
        return afficher_montant(self.solde_centimes)


@dataclass(frozen=True)
class DemandePaiement:
    """Un montant deja calcule par T04, pour une tentative de paiement."""

    id_transaction: str
    montant_centimes: int

    def __post_init__(self):
        valider_id_transaction(self.id_transaction)
        valider_montant(self.montant_centimes)


class TypeOperation(str, Enum):
    PAIEMENT = "PAIEMENT"
    CREDIT = "CREDIT"


class StatutOperation(str, Enum):
    PAIE = "PAIE"
    CREDITE = "CREDITE"
    COMPTE_INCONNU = "COMPTE_INCONNU"
    SOLDE_INSUFFISANT = "SOLDE_INSUFFISANT"


class ConflitTransaction(ValueError):
    """Un ID deja utilise ne peut pas designer une autre operation."""


@dataclass(frozen=True)
class ResultatOperation:
    id_transaction: str
    date_utc: str
    type_operation: TypeOperation
    id_uart: str
    montant_centimes: int
    statut: StatutOperation
    solde_avant_centimes: int | None
    solde_apres_centimes: int | None
    deja_traitee: bool = False

    @property
    def succes(self):
        return self.statut in (StatutOperation.PAIE, StatutOperation.CREDITE)
