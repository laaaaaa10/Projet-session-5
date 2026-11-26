"""
controleur_interface.py

T01 - Enchaînement des écrans de la borne.

  Dépôt   : accueil -> carte (T03) -> place (T03) -> confirmation 60 s (T03)
            -> billet (T05) -> rangement (T11) -> message
  Retrait : accueil -> numéro du billet (T05) -> T04 -> paiement (T02)
            -> récupération (T12) -> message

T01 ne prend aucune décision des autres tâches : il affiche leurs pages,
transmet les demandes et suit les réponses.

 Created on: 25 nov. 2026
      Author: Javier Bolduc
"""

from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtWidgets import QApplication

from interface.src.config import (DELAI_INACTIVITE_S, DELAI_MESSAGE_S, DELAI_OPERATION_S,
                                  DELAI_REFUS_BILLET_S, PERIODE_SUIVI_MS)
from interface.src.hardware.evenements import ETAT_EN_COURS, ETAT_ERREUR, ETAT_TERMINE
from interface.src.models.session import OPERATION_DEPOT, OPERATION_RETRAIT, Session
from modeles.comptes import StatutOperation
from modules.depot import EtapeDepot

RAISONS_REFUS = {
    StatutOperation.COMPTE_INCONNU: "Carte inconnue.",
    StatutOperation.SOLDE_INSUFFISANT: "Solde insuffisant.",
}

# Appuis qui repartent le délai d'inactivité, sur n'importe quelle page
EVENEMENTS_ACTIVITE = (QEvent.Type.MouseButtonPress, QEvent.Type.TouchBegin, QEvent.Type.KeyPress)


class ControleurInterface(QObject):

    def __init__(self, fenetre, services, evenements):
        super().__init__()
        self.f = fenetre
        self.services = services
        self.evenements = evenements
        self.session = Session()
        self.compteur_depot = 0

        # Disponibilité de la borne
        self.lecteur_pret = False                   # T02 : lecteur RFID ouvert
        self.raison_lecteur = "Démarrage du lecteur de cartes…"
        self.en_service = True                      # T13 (pas encore livré)
        self.raison_service = ""

        # Minuteries à un seul déclenchement
        self.minuterie_inactivite = self._creer_minuterie(DELAI_INACTIVITE_S, self.annuler)
        self.minuterie_message = self._creer_minuterie(DELAI_MESSAGE_S, self.retour_accueil)
        self.minuterie_refus = self._creer_minuterie(DELAI_REFUS_BILLET_S, self._nouvelle_saisie)
        self.minuterie_operation = self._creer_minuterie(DELAI_OPERATION_S, self._operation_trop_longue)

        # Mise à jour des modules et suivi du rangement (T11)
        self.minuterie_suivi = QTimer(self)
        self.minuterie_suivi.setInterval(PERIODE_SUIVI_MS)
        self.minuterie_suivi.timeout.connect(self._suivre)
        self.minuterie_suivi.start()

        f = fenetre
        # Écrans de T01
        f.ecran_accueil.bouton_depot.clicked.connect(self.commencer_depot)
        f.ecran_accueil.bouton_retrait.clicked.connect(self.commencer_retrait)
        f.ecran_recuperation.bouton_annuler.clicked.connect(self.annuler)
        f.ecran_message.bouton_ok.clicked.connect(self.retour_accueil)
        f.cadre_reservation.bouton_annuler.clicked.connect(self.annuler)
        f.cadre_saisie_billet.bouton_annuler.clicked.connect(self.annuler)

        # Pages de T03 et T05
        f.page_carte.annulee.connect(self.annuler)
        f.page_carte.carte_acceptee.connect(self.carte_acceptee)
        f.page_reservation.place_reservee.connect(self.place_reservee)
        f.page_confirmation.reservation_annulee.connect(self.annuler)
        f.page_confirmation.reservation_expiree.connect(self.reservation_expiree)
        f.page_confirmation.depot_confirme.connect(self.depot_confirme)
        f.page_billet.billet_confirme.connect(self.billet_confirme)
        f.page_saisie_billet.numero_saisi.connect(self.numero_saisi)

        # Pont T02 (connecté avant son démarrage)
        pont = services.pont_t02
        pont.carte_lue.connect(f.page_carte.recevoir_carte)
        pont.pret.connect(self.lecteur_ouvert)
        pont.erreur.connect(self.erreur_lecteur)
        pont.paiement_en_attente.connect(self.paiement_en_attente)
        pont.resultat_paiement.connect(self.resultat_paiement)
        pont.paiement_annule.connect(self.paiement_annule)

        # Crochets des tâches non livrées
        e = evenements
        e.sig_resultat_retrait.connect(self.resultat_retrait)
        e.sig_etat_operation.connect(self.etat_operation)
        e.sig_etat_service.connect(self.etat_service)
        e.sig_presence_usager.connect(self.presence_usager)

        QApplication.instance().installEventFilter(self)
        self.retour_accueil()

    @property
    def disponible(self):
        return self.lecteur_pret and self.en_service

    # --- Navigation ----------------------------------------------------------

    def retour_accueil(self):
        """Termine l'opération et revient à l'écran d'attente."""
        self._arreter_minuteries()
        self._terminer_session()
        self._afficher_accueil()
        self.f.afficher_ecran("accueil")

    def annuler(self):
        """Bouton Annuler ou délai d'inactivité (impossible une fois la
        transaction créée ou le paiement accepté)."""
        s = self.session
        if s.operation is None or s.en_cours:
            return
        if s.id_paiement is not None:
            self._annuler_paiement(s.id_paiement)
        self.evenements.operation_annulee.emit()
        self.retour_accueil()

    # --- Dépôt ---------------------------------------------------------------

    def commencer_depot(self):
        if not self.disponible:
            return
        self.compteur_depot += 1
        id_session = f"depot-{self.compteur_depot}"
        self.session.commencer(OPERATION_DEPOT, id_session)
        self.f.page_reservation.session_id = id_session
        self.f.page_confirmation.session_id = id_session
        self.f.afficher_ecran("carte")
        self.minuterie_inactivite.start()

    def carte_acceptee(self, info):
        s = self.session
        if s.operation != OPERATION_DEPOT or info is None:
            return
        s.id_uart = info.id_uart
        self.services.cartes[s.id_session] = info.id_uart
        self.f.afficher_ecran("reservation")
        self.minuterie_inactivite.start()

    def place_reservee(self, libelle):
        if self.session.operation != OPERATION_DEPOT:
            return
        self.minuterie_inactivite.stop()            # T03 gère son propre délai de 60 s
        self.f.afficher_ecran("confirmation")

    def reservation_expiree(self):
        if self.session.operation != OPERATION_DEPOT:
            return
        self.evenements.operation_annulee.emit()
        self._afficher_message("Réservation expirée",
                               "Le délai de confirmation est écoulé.\nLa place a été libérée.")

    def depot_confirme(self, transaction_id, place):
        s = self.session
        if s.operation != OPERATION_DEPOT or s.en_cours:
            return
        s.transaction_id, s.place, s.en_cours = transaction_id, place, True
        self.f.afficher_ecran("billet")
        self.f.page_billet.afficher_billet(transaction_id, place)

    def billet_confirme(self, transaction_id):
        s = self.session
        if s.operation != OPERATION_DEPOT or transaction_id != s.transaction_id:
            return
        self.f.ecran_depot.afficher()
        self.f.afficher_ecran("depot")
        self.minuterie_operation.start()
        self.evenements.billet_confirme.emit(transaction_id, s.place)

    # --- Retrait -------------------------------------------------------------

    def commencer_retrait(self):
        if not self.disponible:
            return
        self.session.commencer(OPERATION_RETRAIT)
        self.f.afficher_ecran("saisie_billet")
        self.minuterie_inactivite.start()

    def numero_saisi(self, numero):
        s = self.session
        if s.operation != OPERATION_RETRAIT or s.numero is not None:
            return
        s.numero = numero
        self.minuterie_inactivite.start()           # sans réponse de T04 : retour à l'accueil
        self.evenements.retrait_demande.emit(numero)

    def resultat_retrait(self, trouve, message):
        s = self.session
        if (s.operation != OPERATION_RETRAIT or s.numero is None
                or self.f.ecran_courant() != "saisie_billet"):
            return
        if trouve:
            self.f.ecran_recuperation.afficher()
            self.f.afficher_ecran("recuperation")
        else:
            self.f.page_saisie_billet.afficher_message(
                message or f"Transaction {s.numero:06d} inconnue", ok=False)
            self.minuterie_refus.start()
        self.minuterie_inactivite.start()

    def paiement_en_attente(self, demande):
        s = self.session
        if (s.operation != OPERATION_RETRAIT or s.en_cours
                or self.f.ecran_courant() != "recuperation"):
            return
        s.id_paiement = demande.id_transaction
        self.f.ecran_recuperation.afficher_paiement(demande.montant_centimes)
        self.minuterie_inactivite.start()

    def resultat_paiement(self, resultat):
        s = self.session
        if s.en_cours or s.id_paiement is None or resultat.id_transaction != s.id_paiement:
            return
        if resultat.statut == StatutOperation.PAIE:
            s.en_cours = True
            self.minuterie_inactivite.stop()
            self.f.ecran_recuperation.bouton_annuler.setEnabled(False)
            self.f.ecran_recuperation.afficher_etat("Paiement accepté.\nRécupération de votre véhicule…")
            self.minuterie_operation.start()
        else:
            self._afficher_message("Paiement refusé", RAISONS_REFUS.get(resultat.statut, ""))

    def paiement_annule(self, id_transaction):
        s = self.session
        if s.id_paiement == id_transaction and not s.en_cours:
            self._afficher_message("Paiement annulé", "Le paiement a été annulé.")

    # --- Fin d'opération (T11 suivi ici, T12 par crochet) --------------------

    def etat_operation(self, etat, message):
        s = self.session
        if not s.en_cours:
            return
        depot = s.operation == OPERATION_DEPOT
        if self.f.ecran_courant() != ("depot" if depot else "recuperation"):
            return                                  # ex. billet pas encore confirmé
        if etat == ETAT_EN_COURS:
            ecran = self.f.ecran_depot if depot else self.f.ecran_recuperation
            ecran.afficher_etat(message or "Opération en cours…")
        elif etat == ETAT_TERMINE:
            if depot:
                self._afficher_message("Véhicule rangé", message or "Votre véhicule est rangé.\nMerci !")
            else:
                self._afficher_message("Véhicule prêt", message or "Votre véhicule est prêt.\nMerci !")
        elif etat == ETAT_ERREUR:
            self._afficher_message("Erreur", message or
                                   "L'opération n'a pas pu être complétée.\nContactez le personnel.")

    def _suivre(self):
        """Met à jour les modules et suit le rangement de la transaction en cours (T11)."""
        self.services.mettre_a_jour()
        s = self.session
        depot = self.services.depot
        if (s.operation != OPERATION_DEPOT or not s.en_cours
                or depot.transaction_id != s.transaction_id):
            return                                  # rangement pas encore démarré
        if depot.etape == EtapeDepot.TERMINE:
            self.etat_operation(ETAT_TERMINE, "")
        elif depot.etape in (EtapeDepot.DEFAUT, EtapeDepot.INTERROMPU):
            self.etat_operation(ETAT_ERREUR, "")
        else:
            self.etat_operation(ETAT_EN_COURS, f"Rangement en cours…\n{depot.obtenir_etat()}")

    def _operation_trop_longue(self):
        self._afficher_message("Opération non terminée",
                               "L'opération n'est pas terminée.\nContactez le personnel au besoin.")

    # --- Disponibilité de la borne -------------------------------------------

    def lecteur_ouvert(self, comptes):
        self.lecteur_pret = True
        self._rafraichir_disponibilite()

    def erreur_lecteur(self, incident):
        if incident.fatal:
            self.lecteur_pret = False
            self.raison_lecteur = "Lecteur de cartes indisponible."
            self._rafraichir_disponibilite()

    def etat_service(self, en_service, message):
        self.en_service = en_service
        self.raison_service = message
        self._rafraichir_disponibilite()

    def presence_usager(self, present):
        if self.session.operation is None:
            if self.disponible:
                self.f.ecran_accueil.afficher_presence(present)
        elif present and self.minuterie_inactivite.isActive():
            self.minuterie_inactivite.start()       # l'usager est encore là

    def _rafraichir_disponibilite(self):
        if self.session.operation is None:
            self._afficher_accueil()
        elif not self.disponible:
            self.annuler()                          # sans effet si une transaction est en cours

    def _afficher_accueil(self):
        if self.disponible:
            self.f.ecran_accueil.afficher()
        elif not self.en_service:
            self.f.ecran_accueil.afficher_hors_service(self.raison_service)
        else:
            self.f.ecran_accueil.afficher_hors_service(self.raison_lecteur)

    # --- Interne -------------------------------------------------------------

    def eventFilter(self, objet, evenement):
        if evenement.type() in EVENEMENTS_ACTIVITE and self.minuterie_inactivite.isActive():
            self.minuterie_inactivite.start()
        return False

    def _nouvelle_saisie(self):
        if self.session.operation == OPERATION_RETRAIT and self.f.ecran_courant() == "saisie_billet":
            self.session.numero = None
            self.f.page_saisie_billet.reinitialiser()

    def _afficher_message(self, titre, texte):
        self._arreter_minuteries()
        self._terminer_session()
        self.f.ecran_message.afficher(titre, texte)
        self.f.afficher_ecran("message")
        self.minuterie_message.start()

    def _terminer_session(self):
        """Libère la réservation T03 si le dépôt n'a pas été confirmé, puis oublie la session."""
        s = self.session
        if s.operation == OPERATION_DEPOT:
            if not s.en_cours:
                self.services.reservation.annuler_reservation(s.id_session)
            self.services.reservation.terminer_session(s.id_session)
            self.services.cartes.pop(s.id_session, None)
        s.reinitialiser()

    def _annuler_paiement(self, id_transaction):
        try:
            self.services.pont_t02.annuler_paiement(id_transaction)
        except RuntimeError:
            pass                                    # pont arrêté : aucune attente à annuler

    def _arreter_minuteries(self):
        for minuterie in (self.minuterie_inactivite, self.minuterie_message,
                          self.minuterie_refus, self.minuterie_operation):
            minuterie.stop()

    def _creer_minuterie(self, delai_s, fonction):
        minuterie = QTimer(self)
        minuterie.setSingleShot(True)
        minuterie.setInterval(int(delai_s * 1000))
        minuterie.timeout.connect(fonction)
        return minuterie
