"""Premier incrément T12 : demande et paiement, sans autorisation mécanique.

Le journal conserve les identifiants avant l'appel à T04. Après redémarrage,
une demande non terminée reste interrompue : aucun paiement n'est relancé.
Appeler depuis un seul thread de travail, comme les API T02/T04 existantes.
"""

from enum import Enum
import json
import math
from pathlib import Path
import sqlite3

from api.retrait import (
    DELAI_PAIEMENT_S, InterfaceFacturationRetrait, RetraitRefuse,
    StatutRetrait, SuiviRetrait, TransactionRetrait, valider_id_retrait,
)
from modeles.comptes import StatutOperation, TypeOperation, valider_id_uart, valider_montant


class EtapeDemandeRetrait(str, Enum):
    DEMANDE = "DEMANDE"
    ATTENTE = "ATTENTE_PAIEMENT"
    PAYE = "PAYE_ATTENTE_MECANIQUE"
    EXPIRE = "EXPIRE"
    CLOTURE = "CLOTURE"
    ANNULE = "ANNULE"
    INCERTAIN = "INCERTAIN"
    INTERROMPU = "INTERROMPU"


class GestionDemandeRetrait:
    """Préparation financière destinée au futur GestionRetrait (§9.2).

    id_demande est créé par l'appelant pour une nouvelle action utilisateur,
    puis réutilisé pour toutes ses retransmissions. PAYE n'est pas une preuve
    de disponibilité mécanique. Ce composant n'envoie aucune commande CAN.
    """

    def __init__(self, facturation: InterfaceFacturationRetrait, journal):
        self.facturation = facturation
        self.nouvelles_autorisees = False
        self.derniere_erreur = ""
        Path(journal).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(journal)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")
        with self.db:
            self.db.execute("""CREATE TABLE IF NOT EXISTS demandes (
                id TEXT PRIMARY KEY, numero INTEGER NOT NULL, place INTEGER NOT NULL,
                etape TEXT NOT NULL, fenetre TEXT, paiement TEXT, message TEXT NOT NULL
            )""")
            self.db.execute("""UPDATE demandes SET etape=?, message=?
                WHERE etape NOT IN (?, ?, ?, ?)""", (
                EtapeDemandeRetrait.INTERROMPU.value, "Redémarrage : intervention requise",
                EtapeDemandeRetrait.EXPIRE.value, EtapeDemandeRetrait.ANNULE.value,
                EtapeDemandeRetrait.INTERROMPU.value, EtapeDemandeRetrait.CLOTURE.value,
            ))
        ligne = self.db.execute("SELECT id FROM demandes ORDER BY rowid DESC LIMIT 1").fetchone()
        self.id_demande = None if ligne is None else ligne["id"]

    def autoriser_nouvelles(self, autoriser: bool):
        if type(autoriser) is not bool:
            raise TypeError("Booléen attendu")
        self.nouvelles_autorisees = autoriser

    def instantane(self, id_demande=None):
        ligne = self.db.execute("SELECT * FROM demandes WHERE id=?",
                                (id_demande or self.id_demande,)).fetchone()
        return None if ligne is None else dict(ligne)

    @property
    def etape(self):
        ligne = self.instantane()
        return None if ligne is None else EtapeDemandeRetrait(ligne["etape"])

    @property
    def paiement_valide(self):
        return self.etape == EtapeDemandeRetrait.PAYE

    def _enregistrer(self, etape, message="", *, fenetre=None, paiement=None):
        with self.db:
            self.db.execute("""UPDATE demandes SET etape=?, message=?,
                fenetre=COALESCE(?, fenetre), paiement=COALESCE(?, paiement) WHERE id=?""",
                (etape.value, message, fenetre, paiement, self.id_demande))

    def demander_retrait(self, transaction_id: int, *, id_demande: str) -> bool:
        valider_id_retrait(id_demande)
        # Même validation que la transaction, sans présumer de sa place.
        TransactionRetrait(transaction_id, 1)
        ancien = self.instantane(id_demande)
        if ancien is not None:
            if ancien["numero"] != transaction_id:
                raise ValueError("ID de retrait réutilisé pour une autre transaction")
            return True  # Un ancien ID ne remplace jamais une demande plus récente.
        if not self.nouvelles_autorisees:
            self.derniere_erreur = "Nouvelles demandes interdites"
            return False
        if self.etape not in (None, EtapeDemandeRetrait.EXPIRE, EtapeDemandeRetrait.ANNULE, EtapeDemandeRetrait.CLOTURE):
            self.derniere_erreur = "Demande en cours ou intervention requise"
            return False
        transaction = self.facturation.identifier_transaction(transaction_id)
        if transaction is None:
            self.derniere_erreur = "Transaction inconnue"
            return False
        if not isinstance(transaction, TransactionRetrait) or transaction.numero != transaction_id:
            raise ValueError("Réponse T04 incohérente")
        with self.db:
            self.db.execute("INSERT INTO demandes VALUES (?, ?, ?, ?, NULL, NULL, '')",
                            (id_demande, transaction.numero, transaction.place,
                             EtapeDemandeRetrait.DEMANDE.value))
        self.id_demande = id_demande
        self.derniere_erreur = ""
        return True

    def confirmer_retrait_et_figer_montant(self, id_demande: str) -> bool:
        if id_demande != self.id_demande:
            return False
        if self.etape in (EtapeDemandeRetrait.ATTENTE, EtapeDemandeRetrait.PAYE):
            return True
        if not self.nouvelles_autorisees or self.etape != EtapeDemandeRetrait.DEMANDE:
            return False
        # Intention durable AVANT un appel qui pourrait déjà ouvrir un paiement.
        self._enregistrer(EtapeDemandeRetrait.INCERTAIN, "Confirmation T04 en cours")
        try:
            suivi = self.facturation.figer_montant(self.instantane()["numero"], id_demande)
        except RetraitRefuse as erreur:
            self._enregistrer(EtapeDemandeRetrait.ANNULE, str(erreur))
            return False
        except Exception as erreur:
            self._enregistrer(EtapeDemandeRetrait.INCERTAIN, str(erreur))
            return False
        return self._appliquer(suivi)

    def _appliquer(self, suivi):
        try:
            if not isinstance(suivi, SuiviRetrait):
                raise ValueError("SuiviRetrait attendu")
            ligne, f = self.instantane(), suivi.fenetre
            if (f.id_retrait, f.transaction.numero, f.transaction.place) != (
                    self.id_demande, ligne["numero"], ligne["place"]):
                raise ValueError("Réponse T04 non corrélée")
            valider_montant(f.montant_centimes)
            if (type(f.ouverte_a) not in (int, float) or type(f.expire_a) not in (int, float)
                    or not math.isfinite(f.ouverte_a) or not math.isfinite(f.expire_a)
                    or abs(f.expire_a - f.ouverte_a - DELAI_PAIEMENT_S) > 1e-6):
                raise ValueError("Fenêtre T04 différente de 60 secondes")
            fenetre = json.dumps([f.montant_centimes, f.ouverte_a, f.expire_a])
            if ligne["fenetre"] is not None and json.loads(ligne["fenetre"]) != json.loads(fenetre):
                raise ValueError("Montant ou échéance modifiés pour le même retrait")
            etape = {
                StatutRetrait.ATTENTE: EtapeDemandeRetrait.ATTENTE,
                StatutRetrait.PAYE: EtapeDemandeRetrait.PAYE,
                StatutRetrait.EXPIRE: EtapeDemandeRetrait.EXPIRE,
                StatutRetrait.ANNULE: EtapeDemandeRetrait.ANNULE,
                StatutRetrait.INCERTAIN: EtapeDemandeRetrait.INCERTAIN,
            }[suivi.statut]
            preuve = None
            if suivi.statut == StatutRetrait.PAYE:
                p = suivi.paiement
                if (p is None or p.type_operation != TypeOperation.PAIEMENT
                        or p.statut != StatutOperation.PAIE
                        or p.montant_centimes != f.montant_centimes
                        or type(suivi.valide_a) not in (int, float) or not math.isfinite(suivi.valide_a)
                        or not f.ouverte_a <= suivi.valide_a < f.expire_a):
                    raise ValueError("Paiement intégral dans le délai non prouvé")
                valider_montant(p.montant_centimes)
                valider_id_retrait(p.id_transaction)
                valider_id_uart(p.id_uart)
                valider_montant(p.solde_avant_centimes)
                valider_montant(p.solde_apres_centimes)
                if p.solde_avant_centimes - p.solde_apres_centimes != f.montant_centimes:
                    raise ValueError("Reçu de paiement incohérent")
                preuve = json.dumps({"id_operation": p.id_transaction, "id_uart": p.id_uart,
                                     "montant_centimes": p.montant_centimes})
            elif suivi.paiement is not None:
                raise ValueError("Reçu présent sans état PAYE : réconciliation nécessaire")
        except (AttributeError, KeyError, TypeError, ValueError) as erreur:
            self._enregistrer(EtapeDemandeRetrait.INCERTAIN, str(erreur))
            return False
        self._enregistrer(etape, suivi.message, fenetre=fenetre, paiement=preuve)
        return etape in (EtapeDemandeRetrait.ATTENTE, EtapeDemandeRetrait.PAYE)

    def mettre_a_jour(self):
        if self.etape not in (EtapeDemandeRetrait.ATTENTE, EtapeDemandeRetrait.INCERTAIN):
            return
        try:
            suivi = self.facturation.consulter_retrait(self.id_demande)
        except Exception as erreur:
            self._enregistrer(EtapeDemandeRetrait.INCERTAIN, str(erreur))
            return
        self._appliquer(suivi)

    actualiser = mettre_a_jour

    def annuler(self, id_demande: str) -> bool:
        if id_demande != self.id_demande:
            return False
        if self.etape == EtapeDemandeRetrait.DEMANDE:
            self._enregistrer(EtapeDemandeRetrait.ANNULE)
            return True
        if self.etape in (EtapeDemandeRetrait.ANNULE, EtapeDemandeRetrait.EXPIRE):
            return True
        if self.etape not in (EtapeDemandeRetrait.ATTENTE, EtapeDemandeRetrait.INCERTAIN):
            return False
        try:
            self._appliquer(self.facturation.annuler_retrait(id_demande))
        except Exception as erreur:
            self._enregistrer(EtapeDemandeRetrait.INCERTAIN, str(erreur))
        return self.etape in (EtapeDemandeRetrait.ANNULE, EtapeDemandeRetrait.EXPIRE)

    def arreter(self):
        self.nouvelles_autorisees = False
        if self.etape in (None, EtapeDemandeRetrait.ANNULE, EtapeDemandeRetrait.EXPIRE, EtapeDemandeRetrait.CLOTURE):
            return
        precedente = self.etape
        self._enregistrer(EtapeDemandeRetrait.INTERROMPU, "Intervention requise")
        if precedente in (EtapeDemandeRetrait.ATTENTE, EtapeDemandeRetrait.INCERTAIN):
            try:
                # T04 conserve un éventuel débit déjà effectué. Ne jamais rembourser.
                self.facturation.annuler_retrait(self.id_demande)
            except Exception as erreur:
                self._enregistrer(EtapeDemandeRetrait.INTERROMPU,
                                  f"Intervention requise ; paiement incertain : {erreur}")

    def enregistrer_sortie(self, id_demande):
        """Appelé par T12 uniquement après reçu de clôture corrélé du propriétaire T04."""
        if id_demande != self.id_demande or self.etape not in (EtapeDemandeRetrait.PAYE, EtapeDemandeRetrait.CLOTURE):
            raise ValueError("Demande payée attendue pour constater la clôture T04")
        self._enregistrer(EtapeDemandeRetrait.CLOTURE)

    def obtenir_etat(self):
        ligne = self.instantane()
        return "INACTIF" if ligne is None else ligne["etape"]

    def fermer(self):
        self.db.close()
