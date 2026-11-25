"""
pages_reservation.py - T03 (RPi) : pages PyQt6 de réservation d'une place.

  PageCarte              : « Présentez votre carte » ; affiche le solde, le tarif
                           et la durée maximale (carte lue par T02).
  PageReservation        : les 14 places avec leur couleur d'état ; l'utilisateur
                           touche une place libre pour la réserver.
  PageConfirmationDepot  : place retenue, décompte de 60 s, confirmation ou
                           annulation du dépôt.

QWidget autonomes, enregistrés dans la fenêtre principale de T01. Les pages
ne lisent que le modèle partagé (via GestionReservation) : l'état d'une place
ne dépend jamais de l'état d'un bouton.

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T03)
"""
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from modeles.comptes import afficher_montant
from modules.lecteur_nfc_rfid import numero_badge
from modules.reservation import evaluer_carte
from modules.stationnement import EtatPlace, Presence, numero_place

PERIODE_RAFRAICHISSEMENT_MS = 250

# Couleurs des états (mêmes significations que les DEL des places)
COULEURS = {
    EtatPlace.LIBRE: "#2E9E4F",          # vert
    EtatPlace.RESERVEE: "#2F6FD6",       # bleu
    EtatPlace.OCCUPEE: "#C62828",        # rouge
    EtatPlace.MAINTENANCE: "#EF8A17",    # orange
    EtatPlace.DEFAUT: "#E6C200",         # jaune
}
STYLE_TITRE = "font-size: 26px; font-weight: bold;"
STYLE_TEXTE = "font-size: 20px;"
STYLE_GRAND = "font-size: 56px; font-weight: bold;"
STYLE_BOUTON = "font-size: 22px; padding: 14px;"
STYLE_OK = "font-size: 20px; color: #1D7A3A;"
STYLE_ERREUR = "font-size: 20px; color: #B3261E;"


# =========================================================================== #
# Identification par carte RFID (lecture fournie par T02)                     #
# =========================================================================== #
class PageCarte(QWidget):
    """Attend une carte, puis affiche solde, tarif et durée maximale théorique.

    Brancher : pont_t02.carte_lue.connect(page_carte.recevoir_carte)
    Les lectures reçues quand la page n'est pas affichée sont ignorées
    (une ancienne présentation ne doit pas démarrer un dépôt)."""

    carte_acceptee = pyqtSignal(object)       # InfoCarte
    annulee = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info = None

        self._titre = QLabel("Présentez votre carte")
        self._titre.setStyleSheet(STYLE_TITRE)
        self._details = QLabel("")
        self._details.setStyleSheet(STYLE_TEXTE)
        self._message = QLabel("")
        self._message.setWordWrap(True)
        for widget in (self._titre, self._details, self._message):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._bouton_annuler = QPushButton("Annuler")
        self._bouton_continuer = QPushButton("Choisir une place")
        for bouton in (self._bouton_annuler, self._bouton_continuer):
            bouton.setStyleSheet(STYLE_BOUTON)
        self._bouton_annuler.clicked.connect(self.annulee.emit)
        self._bouton_continuer.clicked.connect(lambda: self.carte_acceptee.emit(self._info))

        boutons = QHBoxLayout()
        boutons.addWidget(self._bouton_annuler)
        boutons.addWidget(self._bouton_continuer)

        disposition = QVBoxLayout(self)
        disposition.addStretch()
        disposition.addWidget(self._titre)
        disposition.addWidget(self._details)
        disposition.addWidget(self._message)
        disposition.addStretch()
        disposition.addLayout(boutons)

    def showEvent(self, evenement):
        self._info = None
        self._titre.setText("Présentez votre carte")
        self._details.setText("Approchez votre carte du lecteur")
        self._message.setText("")
        self._bouton_continuer.setEnabled(False)
        super().showEvent(evenement)

    @pyqtSlot(object)
    def recevoir_carte(self, identification):
        """identification : IdentificationCarte de T02 (id_uart, solde_centimes)."""
        if not self.isVisible():
            return                            # pas en attente d'une carte : ignorée
        info = evaluer_carte(identification.id_uart, identification.solde_centimes)
        self._titre.setText(f"Carte {numero_badge(info.id_uart)}")
        if info.solde_centimes is None:
            self._details.setText("")
        else:
            self._details.setText(
                f"Solde : {afficher_montant(info.solde_centimes)}\n"
                f"Tarif : {afficher_montant(info.tarif_centimes_par_minute)} / minute\n"
                f"Durée maximale : {info.duree_max_min} min")
        if info.acceptee:
            self._info = info
            self._message.setStyleSheet(STYLE_OK)
            self._message.setText("Carte acceptée")
            self._bouton_continuer.setEnabled(True)
        else:
            self._info = None
            self._message.setStyleSheet(STYLE_ERREUR)
            self._message.setText(f"Carte refusée : {info.raison}. Présentez une autre carte.")
            self._bouton_continuer.setEnabled(False)


# =========================================================================== #
# Choix de la place                                                           #
# =========================================================================== #
class PageReservation(QWidget):
    """Grille des 14 places ; une place libre touchée est réservée."""

    place_reservee = pyqtSignal(str)       # libellé, ex. "E1.3"

    def __init__(self, gestion_reservation, parent=None):
        super().__init__(parent)
        self._gr = gestion_reservation
        self.session_id = None             # fixé par la séquence avant l'affichage

        titre = QLabel("Choisissez une place")
        titre.setStyleSheet(STYLE_TITRE)
        titre.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._message = QLabel("")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)

        grille = QGridLayout()
        self._boutons = {}
        for etage in (2, 1):                         # 2e étage en haut, comme la maquette
            ligne = QLabel(f"Étage {etage}")
            ligne.setStyleSheet(STYLE_TEXTE)
            grille.addWidget(ligne, 2 - etage, 0)
            for rang in range(1, 8):
                libelle = f"E{etage}.{rang}"
                bouton = QPushButton(libelle)
                bouton.setMinimumHeight(80)
                bouton.clicked.connect(lambda _, p=libelle: self._choisir(p))
                grille.addWidget(bouton, 2 - etage, rang)
                self._boutons[libelle] = bouton

        legende = QLabel("Vert : libre    Bleu : réservée    Rouge : occupée    "
                         "Orange : maintenance    Jaune : défaut")
        legende.setAlignment(Qt.AlignmentFlag.AlignCenter)

        disposition = QVBoxLayout(self)
        disposition.addWidget(titre)
        disposition.addLayout(grille)
        disposition.addWidget(self._message)
        disposition.addWidget(legende)

        # Le modèle change aussi sans l'utilisateur (IR, autres opérations) : rafraîchir
        self._minuterie = QTimer(self)
        self._minuterie.setInterval(PERIODE_RAFRAICHISSEMENT_MS)
        self._minuterie.timeout.connect(self.rafraichir)

    def rafraichir(self):
        for libelle, info in self._gr.obtenir_places().items():
            bouton = self._boutons[libelle]
            couleur = COULEURS[info["etat"]]
            texte = libelle
            if info["etat"] == EtatPlace.LIBRE and info["presence"] != Presence.ABSENT:
                texte += "\n(vérification)"              # incohérence IR : non réservable
                couleur = "#8A8A8A"                       # gris : libre mais véhicule détecté
            bouton.setText(texte)
            bouton.setEnabled(info["selectionnable"])
            bouton.setStyleSheet(f"font-size: 20px; color: white; background: {couleur};")

    def _choisir(self, libelle):
        if self._gr.reserver_place(libelle, self.session_id):
            self._message.setText("")
            self.place_reservee.emit(libelle)
        else:
            self._message.setStyleSheet(STYLE_ERREUR)
            self._message.setText(f"Réservation impossible : {self._gr.derniere_raison}")
        self.rafraichir()

    def showEvent(self, evenement):
        self._message.setText("")
        self.rafraichir()
        self._minuterie.start()
        super().showEvent(evenement)

    def hideEvent(self, evenement):
        self._minuterie.stop()
        super().hideEvent(evenement)


# =========================================================================== #
# Confirmation du dépôt                                                        #
# =========================================================================== #
class PageConfirmationDepot(QWidget):
    """Place retenue, décompte de 60 s, confirmation ou annulation."""

    depot_confirme = pyqtSignal(int, int)    # (transaction_id, numéro de place 1-14)
    reservation_annulee = pyqtSignal()
    reservation_expiree = pyqtSignal()

    def __init__(self, gestion_reservation, parent=None):
        super().__init__(parent)
        self._gr = gestion_reservation
        self.session_id = None

        self._titre = QLabel("")
        self._titre.setStyleSheet(STYLE_TITRE)
        self._consigne = QLabel("Déposez votre voiture contre la barrière,\npuis confirmez.")
        self._consigne.setStyleSheet(STYLE_TEXTE)
        self._decompte = QLabel("60")
        self._decompte.setStyleSheet(STYLE_GRAND)
        self._message = QLabel("")
        self._message.setWordWrap(True)
        for widget in (self._titre, self._consigne, self._decompte, self._message):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._bouton_annuler = QPushButton("Annuler")
        self._bouton_confirmer = QPushButton("Confirmer le dépôt")
        for bouton in (self._bouton_annuler, self._bouton_confirmer):
            bouton.setStyleSheet(STYLE_BOUTON)
        self._bouton_annuler.clicked.connect(self._annuler)
        self._bouton_confirmer.clicked.connect(self._confirmer)

        boutons = QHBoxLayout()
        boutons.addWidget(self._bouton_annuler)
        boutons.addWidget(self._bouton_confirmer)

        disposition = QVBoxLayout(self)
        disposition.addStretch()
        disposition.addWidget(self._titre)
        disposition.addWidget(self._consigne)
        disposition.addWidget(self._decompte)
        disposition.addWidget(self._message)
        disposition.addStretch()
        disposition.addLayout(boutons)

        self._minuterie = QTimer(self)
        self._minuterie.setInterval(PERIODE_RAFRAICHISSEMENT_MS)
        self._minuterie.timeout.connect(self._suivre_delai)

    def showEvent(self, evenement):
        place = self._gr.place_de(self.session_id) or "?"
        self._titre.setText(f"Place {place} réservée")
        self._message.setText("")
        self._bouton_confirmer.setEnabled(True)
        self._bouton_annuler.setEnabled(True)
        self._suivre_delai()
        self._minuterie.start()
        super().showEvent(evenement)

    def hideEvent(self, evenement):
        self._minuterie.stop()
        super().hideEvent(evenement)

    def _suivre_delai(self):
        expirees = self._gr.mettre_a_jour()
        if self.session_id in expirees:
            self._minuterie.stop()
            self.reservation_expiree.emit()
            return
        self._decompte.setText(f"{int(self._gr.temps_restant(self.session_id) + 0.999)}")

    def _confirmer(self):
        transaction_id = self._gr.confirmer_depot(self.session_id)
        if transaction_id is None:
            self._message.setStyleSheet(STYLE_ERREUR)
            self._message.setText(f"Confirmation impossible : {self._gr.derniere_raison}")
            return
        self._minuterie.stop()
        self._bouton_confirmer.setEnabled(False)
        self._bouton_annuler.setEnabled(False)
        place = self._gr.place_de(self.session_id)
        self.depot_confirme.emit(transaction_id, numero_place(place))

    def _annuler(self):
        self._minuterie.stop()
        self._gr.annuler_reservation(self.session_id)
        self.reservation_annulee.emit()
