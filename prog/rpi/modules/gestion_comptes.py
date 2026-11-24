"""Comptes preconfigures de la borne, charges une fois au demarrage."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path


CHEMIN_COMPTES = Path(__file__).resolve().parent.parent / "donnees" / "comptes.csv"
CHAMPS_CSV = ["id_uart", "nom", "solde_centimes"]


@dataclass(frozen=True)
class Compte:
    id_uart: str
    nom: str
    solde_centimes: int

    @property
    def solde_affiche(self):
        dollars, cents = divmod(self.solde_centimes, 100)
        return f"{dollars},{cents:02d} $"


def charger_comptes(chemin=CHEMIN_COMPTES):
    """Lit le CSV sans le modifier et retourne les comptes par ID UART complet.

    Un fichier absent ou invalide provoque une erreur au demarrage.
    Une carte inconnue ne cree jamais de compte automatiquement.
    """
    comptes = {}
    with Path(chemin).open("r", encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.DictReader(fichier)
        if lecteur.fieldnames != CHAMPS_CSV:
            raise ValueError(
                "CSV des comptes : en-tete attendu " + ",".join(CHAMPS_CSV)
            )

        for ligne in lecteur:
            contexte = f"CSV des comptes, ligne {lecteur.line_num}"
            if None in ligne or any(ligne[champ] is None for champ in CHAMPS_CSV):
                raise ValueError(f"{contexte} : il faut exactement trois colonnes")

            identifiant = ligne["id_uart"].strip().upper()
            nom = ligne["nom"].strip()
            if re.fullmatch(r"[0-9A-F]{10}", identifiant) is None:
                raise ValueError(f"{contexte} : ID UART invalide (10 chiffres hexadecimaux)")
            if identifiant in comptes:
                raise ValueError(f"{contexte} : ID UART en double : {identifiant}")
            if not nom:
                raise ValueError(f"{contexte} : nom manquant")

            try:
                solde = int(ligne["solde_centimes"])
            except ValueError as erreur:
                raise ValueError(f"{contexte} : solde attendu en centimes entiers") from erreur
            if solde < 0:
                raise ValueError(f"{contexte} : le solde ne peut pas etre negatif")

            comptes[identifiant] = Compte(identifiant, nom, solde)

    return comptes
