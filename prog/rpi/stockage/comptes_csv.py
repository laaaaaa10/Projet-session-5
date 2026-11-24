"""CSV locaux : verrou interprocessus, journal durable et soldes recuperables.

Le journal est la reference des operations confirmees. Il est remplace avant
le fichier de soldes ; une interruption entre les deux est reparee a la lecture.
Ce stockage est destine au systeme de fichiers local Linux du Raspberry Pi.
"""

from contextlib import contextmanager
import csv
from dataclasses import replace
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import tempfile

from modeles.comptes import (
    Compte, ResultatOperation, StatutOperation, TypeOperation,
    valider_id_transaction, valider_id_uart, valider_montant,
)


RACINE_DONNEES = Path(__file__).resolve().parents[1] / "donnees"
CHEMIN_MODELE = RACINE_DONNEES / "comptes.csv"
DOSSIER_ACTIF = RACINE_DONNEES / "actives"
CHAMPS_COMPTES = ["id_uart", "nom", "solde_centimes"]
CHAMPS_OPERATIONS = [
    "id_transaction", "date_utc", "type_operation", "id_uart", "montant_centimes",
    "statut", "solde_avant_centimes", "solde_apres_centimes",
]


class ErreurStockage(RuntimeError):
    """Stockage indisponible/incoherent : ne pas annoncer un paiement reussi."""


def _lire_csv(chemin, champs):
    with chemin.open("r", encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.DictReader(fichier, strict=True)
        if lecteur.fieldnames != champs:
            raise ValueError(f"{chemin.name} : en-tete attendu {','.join(champs)}")
        for ligne in lecteur:
            if None in ligne or any(ligne[c] is None for c in champs):
                raise ValueError(f"{chemin.name}, ligne {lecteur.line_num} : colonnes invalides")
            yield ligne


def charger_comptes(chemin=CHEMIN_MODELE):
    """Lit un CSV de comptes (modele ou instantane), sans l'ecrire."""
    comptes = {}
    for ligne in _lire_csv(Path(chemin), CHAMPS_COMPTES):
        identifiant = valider_id_uart(ligne["id_uart"].strip())
        nom = ligne["nom"].strip()
        solde = valider_montant(int(ligne["solde_centimes"]))
        if identifiant in comptes or not nom:
            raise ValueError("Compte duplique ou nom manquant : " + identifiant)
        comptes[identifiant] = Compte(identifiant, nom, solde)
    if not comptes:
        raise ValueError("Le fichier des comptes est vide")
    return comptes


def _ecrire_csv_atomique(chemin, champs, lignes):
    """Ecrire integralement puis remplacer ; ne jamais tronquer le CSV actif."""
    temporaire = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=chemin.parent,
            prefix="." + chemin.name + ".", suffix=".tmp", delete=False,
        ) as fichier:
            temporaire = Path(fichier.name)
            auteur = csv.DictWriter(fichier, fieldnames=champs)
            auteur.writeheader()
            auteur.writerows(lignes)
            fichier.flush()
            os.fsync(fichier.fileno())
        os.replace(temporaire, chemin)
        dossier = os.open(chemin.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dossier)
        finally:
            os.close(dossier)
    finally:
        if temporaire is not None:
            temporaire.unlink(missing_ok=True)


def _ecrire_comptes(chemin, comptes):
    _ecrire_csv_atomique(chemin, CHAMPS_COMPTES, (
        {"id_uart": c.id_uart, "nom": c.nom, "solde_centimes": c.solde_centimes}
        for c in comptes.values()
    ))


def _ligne_operation(resultat):
    ligne = {champ: getattr(resultat, champ) for champ in CHAMPS_OPERATIONS}
    ligne["type_operation"] = resultat.type_operation.value
    ligne["statut"] = resultat.statut.value
    return ligne


def _charger_operations(chemin, comptes):
    operations, derniers_soldes = {}, {}
    for ligne in _lire_csv(chemin, CHAMPS_OPERATIONS):
        identifiant = valider_id_transaction(ligne["id_transaction"])
        if identifiant in operations:
            raise ValueError("Transaction dupliquee dans le journal : " + identifiant)
        type_operation = TypeOperation(ligne["type_operation"])
        id_uart = valider_id_uart(ligne["id_uart"])
        montant = valider_montant(int(ligne["montant_centimes"]),
                                 credit=type_operation == TypeOperation.CREDIT)
        statut = StatutOperation(ligne["statut"])
        date = datetime.fromisoformat(ligne["date_utc"])
        if date.tzinfo is None or date.utcoffset() != timezone.utc.utcoffset(date):
            raise ValueError("Le journal exige une date UTC explicite")
        avant = None if ligne["solde_avant_centimes"] == "" else int(ligne["solde_avant_centimes"])
        apres = None if ligne["solde_apres_centimes"] == "" else int(ligne["solde_apres_centimes"])
        if statut == StatutOperation.COMPTE_INCONNU:
            if id_uart in comptes or avant is not None or apres is not None:
                raise ValueError("Operation de compte inconnu incoherente")
        else:
            if id_uart not in comptes:
                raise ValueError("Un compte du journal a disparu : " + id_uart)
            valider_montant(avant)
            valider_montant(apres)
            if id_uart in derniers_soldes and avant != derniers_soldes[id_uart]:
                raise ValueError("Rupture de la suite des soldes : " + id_uart)
            if type_operation == TypeOperation.CREDIT:
                attendu, solde_attendu = StatutOperation.CREDITE, avant + montant
            elif avant >= montant:
                attendu, solde_attendu = StatutOperation.PAIE, avant - montant
            else:
                attendu, solde_attendu = StatutOperation.SOLDE_INSUFFISANT, avant
            if statut != attendu or apres != solde_attendu:
                raise ValueError("Montant, resultat ou solde incoherent dans le journal")
            derniers_soldes[id_uart] = apres
        operations[identifiant] = ResultatOperation(
            identifiant, ligne["date_utc"], type_operation, id_uart, montant, statut, avant, apres,
        )
    return operations, derniers_soldes


class TransactionCSV:
    """Vue reservee au service, valide pendant le verrou du depot."""

    def __init__(self, depot, comptes, operations):
        self.depot, self.comptes, self.operations = depot, comptes, operations

    def enregistrer(self, resultat):
        if resultat.id_transaction in self.operations:
            raise ValueError("Transaction deja enregistree")
        operations = dict(self.operations)
        operations[resultat.id_transaction] = resultat
        # Le resultat et son nouveau solde deviennent persistants ensemble.
        _ecrire_csv_atomique(self.depot.journal, CHAMPS_OPERATIONS,
                            (_ligne_operation(r) for r in operations.values()))
        self.operations = operations
        if resultat.solde_apres_centimes is not None:
            self.comptes[resultat.id_uart] = replace(
                self.comptes[resultat.id_uart], solde_centimes=resultat.solde_apres_centimes,
            )
            _ecrire_comptes(self.depot.comptes, self.comptes)


class DepotComptesCSV:
    def __init__(self, dossier=DOSSIER_ACTIF, modele=CHEMIN_MODELE):
        self.dossier = Path(dossier)
        self.modele = Path(modele)
        self.comptes = self.dossier / "comptes.csv"
        self.journal = self.dossier / "operations.csv"

    def _initialiser(self):
        if self.comptes.exists() and not self.journal.exists():
            raise ValueError("Journal absent : restauration necessaire, historique non recree")
        if not self.journal.exists():
            charger_comptes(self.modele)
            _ecrire_csv_atomique(self.journal, CHAMPS_OPERATIONS, [])
        if not self.comptes.exists():
            if list(_lire_csv(self.journal, CHAMPS_OPERATIONS)):
                raise ValueError("Fichier des comptes absent alors que le journal contient des operations")
            _ecrire_comptes(self.comptes, charger_comptes(self.modele))

    @contextmanager
    def transaction(self):
        try:
            self.dossier.mkdir(parents=True, exist_ok=True)
            # Fichier distinct : le verrou survit au remplacement des CSV.
            with (self.dossier / "comptes.lock").open("a") as verrou:
                fcntl.flock(verrou, fcntl.LOCK_EX)
                try:
                    try:
                        self._initialiser()
                        comptes = charger_comptes(self.comptes)
                        operations, soldes = _charger_operations(self.journal, comptes)
                    except ValueError as erreur:
                        raise ErreurStockage(f"{self.dossier} : donnees invalides : {erreur}") from erreur
                    corriger = False
                    for id_uart, solde in soldes.items():
                        if comptes[id_uart].solde_centimes != solde:
                            comptes[id_uart] = replace(comptes[id_uart], solde_centimes=solde)
                            corriger = True
                    if corriger:
                        _ecrire_comptes(self.comptes, comptes)
                    yield TransactionCSV(self, comptes, operations)
                finally:
                    fcntl.flock(verrou, fcntl.LOCK_UN)
        except (OSError, csv.Error, UnicodeError) as erreur:
            raise ErreurStockage(
                f"{self.dossier} : {erreur}. Si une operation etait en cours, "
                "reessayer avec le MEME ID de transaction."
            ) from erreur
