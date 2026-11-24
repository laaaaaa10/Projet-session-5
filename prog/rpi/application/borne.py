"""Relie les evenements RFID, les demandes de T04 et le service de comptes."""

from dataclasses import replace
from threading import RLock
import time

from modeles.comptes import ConflitTransaction, DemandePaiement, TypeOperation


class PaiementEnCours(RuntimeError):
    """La borne attend deja une carte pour une autre demande."""


class Borne:
    def __init__(self, comptes, affichage):
        self.comptes = comptes
        self.affichage = affichage
        self._demande = None
        self._resultats = []
        self._verrou = RLock()

    def demander_paiement(self, demande):
        """Point d'entree T04. Une seule tentative peut attendre une carte."""
        if not isinstance(demande, DemandePaiement):
            raise TypeError("DemandePaiement attendue")
        with self._verrou:
            if self._demande is not None:
                if self._demande == demande:
                    return
                if self._demande.id_transaction == demande.id_transaction:
                    raise ConflitTransaction("Montant modifie pour une demande deja en attente")
                raise PaiementEnCours("Une demande de paiement attend deja un badge")
            ancien = self.comptes.retrouver_operation(demande.id_transaction)
            if ancien is not None:
                if (ancien.type_operation, ancien.montant_centimes) != (
                    TypeOperation.PAIEMENT, demande.montant_centimes,
                ):
                    raise ConflitTransaction("ID deja utilise avec d'autres donnees")
                self._publier(replace(ancien, deja_traitee=True))
                return
            self._demande = demande
            self.affichage.attente_paiement(demande)

    def annuler_paiement(self, id_transaction):
        """Annule seulement une attente. Un paiement termine n'est pas rembourse."""
        with self._verrou:
            if self._demande is None or self._demande.id_transaction != id_transaction:
                return False
            self._demande = None
            self.affichage.annulation(id_transaction)
            return True

    def lire_resultats_paiement(self):
        """Point de sortie T04 : retire et retourne les resultats disponibles."""
        with self._verrou:
            resultats, self._resultats = self._resultats, []
            return resultats

    def _publier(self, resultat):
        self._resultats.append(resultat)
        self.affichage.resultat_paiement(resultat)

    def traiter_evenement(self, evenement):
        self.affichage.evenement_rfid(evenement)
        if evenement.type != "ACCEPTE":
            return
        with self._verrou:
            if self._demande is None:
                compte = self.comptes.consulter_compte(evenement.identifiant)
                self.affichage.compte(evenement.identifiant, compte)
                return
            demande = self._demande
            # Si le stockage echoue, l'exception remonte et l'ID reste disponible
            # pour une relance. Ne jamais transformer une erreur en refus definitif.
            resultat = self.comptes.payer(
                demande.id_transaction, evenement.identifiant, demande.montant_centimes,
            )
            self._demande = None
            self._publier(resultat)

    def executer(self, lecteur, *, un_paiement=False):
        """Boucle commune au programme normal et au simulateur de demande T04."""
        while True:
            if un_paiement and self._resultats:
                return
            for evenement in lecteur.lire():
                self.traiter_evenement(evenement)
                if un_paiement and self._resultats:
                    return
            time.sleep(0.002)
