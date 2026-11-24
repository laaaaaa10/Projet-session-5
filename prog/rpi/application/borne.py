"""Relie les evenements RFID, les demandes de T04 et le service de comptes."""

from dataclasses import replace
from threading import RLock
import time

from api.paiements import ModuleT04
from api.identification import ModuleT03
from application.acces_identification import AccesIdentification
from modeles.comptes import (
    ConflitTransaction, DemandePaiement, PaiementEnCours, ResultatOperation,
    TypeOperation, valider_id_transaction,
)


class Borne:
    def __init__(self, comptes, affichage, *, identification: AccesIdentification | None = None):
        self.comptes = comptes
        self.affichage = affichage
        self._identification = identification
        self._demande = None
        self._resultats = []
        self._verrou = RLock()

    def demander_paiement(self, demande: DemandePaiement) -> None:
        """Point d'entree T04. Une seule tentative peut attendre une carte."""
        if not isinstance(demande, DemandePaiement):
            raise TypeError("DemandePaiement attendue")
        with self._verrou:
            ancien = self.comptes.retrouver_operation(demande.id_transaction)
            if ancien is not None:
                if (ancien.type_operation, ancien.montant_centimes) != (
                    TypeOperation.PAIEMENT, demande.montant_centimes,
                ):
                    raise ConflitTransaction("ID deja utilise avec d'autres donnees")
                if self._demande is not None and self._demande.id_transaction == demande.id_transaction:
                    self._demande = None
                self._publier(replace(ancien, deja_traitee=True))
                return
            if self._demande is not None:
                if self._demande == demande:
                    return
                if self._demande.id_transaction == demande.id_transaction:
                    raise ConflitTransaction("Montant modifie pour une demande deja en attente")
                raise PaiementEnCours("Une demande de paiement attend deja un badge")
            self._demande = demande
            self.affichage.attente_paiement(demande)

    def retrouver_resultat_paiement(self, id_transaction: str) -> ResultatOperation | None:
        """Consulte le resultat persistant sans consommer les notifications T04."""
        with self._verrou:
            resultat = self.comptes.retrouver_operation(id_transaction)
            if resultat is None:
                return None
            if resultat.type_operation != TypeOperation.PAIEMENT:
                raise ConflitTransaction("Cet ID designe un credit, pas un paiement")
            return replace(resultat, deja_traitee=True)

    def annuler_paiement(self, id_transaction: str) -> bool:
        """Annule seulement une attente. Un paiement termine n'est pas rembourse."""
        valider_id_transaction(id_transaction)
        with self._verrou:
            if self._demande is None or self._demande.id_transaction != id_transaction:
                return False
            # Une erreur apres l'ecriture du journal peut avoir laisse l'attente
            # en memoire alors que le paiement est deja termine.
            resultat = self.retrouver_resultat_paiement(id_transaction)
            if resultat is not None:
                self._demande = None
                self._publier(resultat)
                return False
            self._demande = None
            self.affichage.annulation(id_transaction)
            return True

    def lire_resultats_paiement(self) -> list[ResultatOperation]:
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
                if self._identification is not None:
                    self._identification._publier(evenement.identifiant, compte)
                return
            demande = self._demande
            # Si le stockage echoue, l'exception remonte et l'ID reste disponible
            # pour une relance. Ne jamais transformer une erreur en refus definitif.
            resultat = self.comptes.payer(
                demande.id_transaction, evenement.identifiant, demande.montant_centimes,
            )
            self._demande = None
            self._publier(resultat)

    def executer(self, lecteur, *, un_paiement=False,
                 t03: ModuleT03 | None = None, t04: ModuleT04 | None = None):
        """Une seule boucle RFID ; les modules branches recoivent leur traitement."""
        if un_paiement and (t03 is not None or t04 is not None):
            raise ValueError("Le test d'un paiement se lance sans les modules T03 et T04")
        while True:
            if un_paiement and self._resultats:
                return
            for evenement in lecteur.lire():
                self.traiter_evenement(evenement)
                if un_paiement and self._resultats:
                    return
            if t03 is not None:
                t03.actualiser()
            if t04 is not None:
                t04.actualiser()
            time.sleep(0.002)
