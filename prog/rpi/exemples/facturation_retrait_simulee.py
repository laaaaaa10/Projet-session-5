"""Double T04 pour les essais T12 ; jamais activé dans l'application réelle.

Les transactions et fenêtres sont simulées EN MÉMOIRE. Les débits passent
exclusivement par InterfacePaiement/T02. Un banc doit appeler
avant_presentation() AVANT chaque événement RFID, apres_presentation()
à sa fin (même sur exception), puis actualiser().
Ce séquencement de banc n'est pas un raccordement du lecteur réel.
"""

from hashlib import sha256
import math
import time

from api.paiements import DemandePaiement, InterfacePaiement, StatutOperation
from api.retrait import (
    DELAI_PAIEMENT_S, FenetreRetrait, RetraitRefuse, StatutRetrait,
    SuiviRetrait, TransactionRetrait, valider_id_retrait,
)
from modeles.comptes import valider_montant


class FacturationRetraitSimulee:
    simulation = True

    def __init__(self, paiements: InterfacePaiement, *, horloge=time.monotonic):
        self.paiements = paiements
        self.horloge = horloge
        self.transactions = {}
        self.dossiers = {}
        self.courant = None
        self.gels = 0

    def ajouter_transaction(self, numero, place, *, depose_a, tarif_centimes=100):
        transaction = TransactionRetrait(numero, place)
        valider_montant(tarif_centimes)
        if numero in self.transactions:
            raise ValueError("Transaction simulée déjà définie")
        if not math.isfinite(depose_a) or depose_a > self.horloge():
            raise ValueError("Date de dépôt simulée invalide")
        self.transactions[numero] = (transaction, depose_a, tarif_centimes)

    def identifier_transaction(self, transaction_id):
        entree = self.transactions.get(transaction_id)
        return None if entree is None else entree[0]

    def montant_courant(self, transaction_id):
        _, debut, tarif = self.transactions[transaction_id]
        return math.ceil(max(0, self.horloge() - debut) / 60) * tarif

    def figer_montant(self, transaction_id, id_retrait):
        valider_id_retrait(id_retrait)
        if id_retrait in self.dossiers:
            if self.dossiers[id_retrait]["suivi"].fenetre.transaction.numero != transaction_id:
                raise RetraitRefuse("ID de retrait réutilisé")
            return self.consulter_retrait(id_retrait)
        transaction = self.identifier_transaction(transaction_id)
        if transaction is None:
            raise RetraitRefuse("Transaction inconnue")
        self.actualiser()
        for d in self.dossiers.values():
            s = d["suivi"]
            if s.statut in (StatutRetrait.ATTENTE, StatutRetrait.INCERTAIN):
                raise RetraitRefuse("Un paiement attend déjà une carte")
            if s.fenetre.transaction.numero == transaction_id and s.statut == StatutRetrait.PAYE:
                raise RetraitRefuse("Transaction déjà payée")
        debut = self.horloge()
        fenetre = FenetreRetrait(id_retrait, transaction, self.montant_courant(transaction_id),
                                debut, debut + DELAI_PAIEMENT_S)
        d = {"suivi": SuiviRetrait(fenetre, StatutRetrait.ATTENTE),
             "tentative": 0, "id_paiement": None, "admis_a": None, "valide_a": None}
        self.dossiers[id_retrait] = d
        self.courant = id_retrait
        self.gels += 1
        self._nouvelle_tentative(d)
        return d["suivi"]

    def _statut(self, d, statut, *, paiement=None, valide_a=None, message=""):
        d["suivi"] = SuiviRetrait(d["suivi"].fenetre, statut, paiement, valide_a, message)

    def _nouvelle_tentative(self, d):
        d["tentative"] += 1
        cle = sha256(d["suivi"].fenetre.id_retrait.encode()).hexdigest()
        d["id_paiement"] = f"t04-sim-{cle}-{d['tentative']}"
        d["admis_a"] = None
        d["valide_a"] = None
        self._statut(d, StatutRetrait.ATTENTE)
        try:
            self.paiements.demander_paiement(DemandePaiement(
                d["id_paiement"], d["suivi"].fenetre.montant_centimes))
        except Exception as erreur:
            self._statut(d, StatutRetrait.INCERTAIN, message=str(erreur))

    def _reconcilier(self, d):
        resultat = self.paiements.retrouver_resultat_paiement(d["id_paiement"])
        if resultat is None:
            return None
        if resultat.statut == StatutOperation.PAIE:
            f = d["suivi"].fenetre
            if (d["admis_a"] is None or d["valide_a"] is None
                    or not f.ouverte_a <= d["admis_a"] <= d["valide_a"] < f.expire_a):
                self._statut(d, StatutRetrait.INCERTAIN,
                             message="Débit observé sans validation complète dans le délai")
            else:
                self._statut(d, StatutRetrait.PAYE, paiement=resultat, valide_a=d["valide_a"])
            return True  # Un débit observé interdit toujours une autre tentative.
        return False

    def _terminer_attente(self, d, statut):
        self.paiements.annuler_paiement(d["id_paiement"])
        # False ne prouve pas l'absence de débit ; relire le journal via l'API.
        if self._reconcilier(d) is not True:
            self._statut(d, statut)

    def actualiser(self):
        if self.courant is None:
            return
        d = self.dossiers[self.courant]
        if d["suivi"].statut not in (StatutRetrait.ATTENTE, StatutRetrait.INCERTAIN):
            return
        try:
            # Seul ce double T04 consomme les notifications dans ce banc isolé.
            self.paiements.lire_resultats_paiement()
            resultat = self._reconcilier(d)
            if resultat is True:
                return
            if self.horloge() >= d["suivi"].fenetre.expire_a:
                self._terminer_attente(d, StatutRetrait.EXPIRE)
            elif resultat is False:
                # Un refus terminé nécessite un NOUVEL ID T02 ; même gel, même délai.
                self._nouvelle_tentative(d)
        except Exception as erreur:
            self._statut(d, StatutRetrait.INCERTAIN, message=str(erreur))

    def avant_presentation(self):
        """Admission du banc AVANT le débit ; à 60.000 s, la carte est refusée.

        À raccorder à un vrai garde d'échéance dans le thread propriétaire du
        lecteur avant un essai réel. Borne.actualiser() seul n'assure pas cela.
        """
        self.actualiser()
        if self.courant is None:
            return False
        d = self.dossiers[self.courant]
        if d["suivi"].statut != StatutRetrait.ATTENTE:
            return False
        maintenant = self.horloge()
        if maintenant >= d["suivi"].fenetre.expire_a:
            self.actualiser()
            return False
        d["admis_a"] = maintenant
        return True

    def apres_presentation(self):
        """Le banc horodate la fin de l'appel synchrone T02, sans présumer son succès."""
        if self.courant is not None:
            d = self.dossiers[self.courant]
            if d["admis_a"] is not None:
                d["valide_a"] = self.horloge()

    def consulter_retrait(self, id_retrait):
        self.actualiser()
        return self.dossiers[id_retrait]["suivi"]

    def annuler_retrait(self, id_retrait):
        d = self.dossiers[id_retrait]
        if d["suivi"].statut in (StatutRetrait.ATTENTE, StatutRetrait.INCERTAIN):
            try:
                self._terminer_attente(d, StatutRetrait.ANNULE)
            except Exception as erreur:
                self._statut(d, StatutRetrait.INCERTAIN, message=str(erreur))
        return d["suivi"]
