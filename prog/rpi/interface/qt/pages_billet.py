"""
pages_billet.py - T05 (RPi) : pages PyQt6 du billet.

  PageBillet        : dépôt - affiche le numéro, l'état de l'impression et
                      demande la confirmation (billet reçu / numéro noté).
  PageSaisieBillet  : retrait - lecture du code-barres ou saisie manuelle
                      du numéro à 6 chiffres, transmis ensuite à T04.

Ces pages sont des QWidget autonomes, enregistrés dans la fenêtre principale
de T01 : elles ne créent pas de QApplication et ne décident ni de l'ouverture
de la barrière (T03) ni de la validité d'une transaction (T04).

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T05)
"""
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QVBoxLayout, QWidget)

from modules.billets import EtatImpression
from modules.lecteur_code_barres import LONGUEUR_NUMERO, LecteurCodeBarres

PERIODE_SUIVI_MS = 200          # rafraîchissement de l'état de l'impression

STYLE_TITRE = "font-size: 26px; font-weight: bold;"
STYLE_NUMERO = "font-size: 64px; font-weight: bold; letter-spacing: 6px;"
STYLE_TEXTE = "font-size: 20px;"
STYLE_BOUTON = "font-size: 22px; padding: 14px;"
STYLE_OK = "font-size: 20px; color: #1D7A3A;"
STYLE_ERREUR = "font-size: 20px; color: #B3261E;"


# =========================================================================== #
# Dépôt : affichage du numéro et confirmation du billet                       #
# =========================================================================== #
class PageBillet(QWidget):
    """Affiche le numéro de transaction et suit l'impression du billet."""

    # Émis quand l'utilisateur confirme avoir reçu le billet ou noté le numéro.
    # T03 l'utilise pour autoriser l'ouverture de la barrière.
    billet_confirme = pyqtSignal(int)          # numéro de transaction

    def __init__(self, gestion_billets, parent=None):
        super().__init__(parent)
        self._billets = gestion_billets
        self._transaction = None
        self._place = None
        self._sequence = None

        self._titre = QLabel("Votre numéro de transaction")
        self._numero = QLabel("------")
        self._detail = QLabel("")
        self._etat = QLabel("")
        self._bouton_confirmer = QPushButton("J'ai reçu mon billet")
        self._bouton_reimprimer = QPushButton("Réimprimer")

        self._titre.setStyleSheet(STYLE_TITRE)
        self._numero.setStyleSheet(STYLE_NUMERO)
        self._detail.setStyleSheet(STYLE_TEXTE)
        for widget in (self._titre, self._numero, self._detail, self._etat):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._etat.setWordWrap(True)
        for bouton in (self._bouton_confirmer, self._bouton_reimprimer):
            bouton.setStyleSheet(STYLE_BOUTON)

        boutons = QHBoxLayout()
        boutons.addWidget(self._bouton_reimprimer)
        boutons.addWidget(self._bouton_confirmer)

        disposition = QVBoxLayout(self)
        disposition.addStretch()
        disposition.addWidget(self._titre)
        disposition.addWidget(self._numero)
        disposition.addWidget(self._detail)
        disposition.addWidget(self._etat)
        disposition.addStretch()
        disposition.addLayout(boutons)

        self._bouton_confirmer.clicked.connect(self._confirmer)
        self._bouton_reimprimer.clicked.connect(self._reimprimer)

        # Suivi non bloquant de l'impression (remplace toute attente active)
        self._minuterie = QTimer(self)
        self._minuterie.setInterval(PERIODE_SUIVI_MS)
        self._minuterie.timeout.connect(self._suivre_impression)

        self._mettre_boutons(confirmer=False, reimprimer=False)

    # --------------------------------------------------------- API publique
    def afficher_billet(self, transaction_id: int, place: int) -> None:
        """Appelée par la séquence de dépôt (T03/T04) : affiche et imprime le billet."""
        self._transaction = transaction_id
        self._place = place
        self._numero.setText(f"{transaction_id:06d}")      # toujours affiché
        self._detail.setText(f"Place {self._libelle_place(place)}")
        self._lancer_impression()

    # ------------------------------------------------------------- interne
    @staticmethod
    def _libelle_place(place):
        return f"E{1 + (place - 1) // 7}.{1 + (place - 1) % 7}"

    def _lancer_impression(self):
        self._mettre_boutons(confirmer=False, reimprimer=False)
        self._afficher_etat("Impression du billet en cours...", ok=True)
        try:
            self._sequence = self._billets.demander_impression(
                self._transaction, self._place, datetime.now())
        except Exception as erreur:                         # bus CAN indisponible...
            self._sequence = None
            self._afficher_echec(f"Impression impossible ({erreur})")
            return
        self._minuterie.start()

    def _suivre_impression(self):
        self._billets.mettre_a_jour()
        etat = self._billets.etat_brut(self._sequence)
        if not etat.est_finale:
            return
        self._minuterie.stop()
        if etat == EtatImpression.ENVOYEE:
            self._afficher_etat("Prenez votre billet.", ok=True)
            self._bouton_confirmer.setText("J'ai reçu mon billet")
            self._mettre_boutons(confirmer=True, reimprimer=True)
        else:
            self._afficher_echec(f"Problème d'impression : "
                                 f"{self._billets.obtenir_etat(self._sequence)}")

    def _afficher_echec(self, message):
        # Le numéro reste affiché : l'utilisateur peut le noter (énoncé ESA)
        self._afficher_etat(f"{message}\nNotez votre numéro avant de continuer.", ok=False)
        self._bouton_confirmer.setText("J'ai noté le numéro")
        self._mettre_boutons(confirmer=True, reimprimer=True)

    def _afficher_etat(self, texte, ok):
        self._etat.setText(texte)
        self._etat.setStyleSheet(STYLE_OK if ok else STYLE_ERREUR)

    def _mettre_boutons(self, confirmer, reimprimer):
        self._bouton_confirmer.setEnabled(confirmer)
        self._bouton_reimprimer.setEnabled(reimprimer)

    def _reimprimer(self):
        # Réimpression explicite : nouvelle séquence, même transaction
        self._lancer_impression()

    def _confirmer(self):
        self._mettre_boutons(confirmer=False, reimprimer=False)   # un seul clic
        self.billet_confirme.emit(self._transaction)


# =========================================================================== #
# Retrait : lecture du code-barres ou saisie manuelle                          #
# =========================================================================== #
class PageSaisieBillet(QWidget):
    """Lecture USB ou saisie manuelle du numéro de billet."""

    # Émis avec un numéro au bon format ; T04 vérifie que la transaction existe.
    numero_saisi = pyqtSignal(int)

    # Signal interne : transporte une lecture du fil evdev vers le fil Qt
    _lecture_recue = pyqtSignal(object, str)

    def __init__(self, nom_lecteur=None, parent=None):
        super().__init__(parent)
        self._occupe = False        # ignore les lectures pendant le traitement
        self._lecteur = LecteurCodeBarres(rappel=self._lecture_recue.emit,
                                          nom_peripherique=nom_lecteur)
        self._lecture_recue.connect(self._traiter_lecture)

        titre = QLabel("Scannez votre billet\nou entrez votre numéro")
        titre.setStyleSheet(STYLE_TITRE)
        titre.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._champ = QLineEdit()
        self._champ.setMaxLength(LONGUEUR_NUMERO)
        self._champ.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._champ.setStyleSheet("font-size: 40px; letter-spacing: 6px;")
        self._champ.setPlaceholderText("_ _ _ _ _ _")
        self._champ.returnPressed.connect(self._valider_manuel)

        self._message = QLabel("")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)

        # Pavé numérique tactile (écran sans clavier)
        pave = QGridLayout()
        touches = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "←", "0", "OK"]
        for i, texte in enumerate(touches):
            bouton = QPushButton(texte)
            bouton.setStyleSheet(STYLE_BOUTON)
            bouton.clicked.connect(lambda _, t=texte: self._touche(t))
            pave.addWidget(bouton, i // 3, i % 3)

        disposition = QVBoxLayout(self)
        disposition.addWidget(titre)
        disposition.addWidget(self._champ)
        disposition.addWidget(self._message)
        disposition.addLayout(pave)

    # --------------------------------------------------------- API publique
    def reinitialiser(self) -> None:
        """Appelée après le traitement par T04 : prête pour une nouvelle lecture."""
        self._occupe = False
        self._champ.clear()
        lecteur_ok = self._lecteur.est_disponible()
        self._afficher("" if lecteur_ok else
                       "Lecteur de codes-barres indisponible : saisie manuelle", ok=lecteur_ok)

    def afficher_message(self, texte: str, ok: bool = True) -> None:
        """Permet à T04 d'afficher sa réponse (ex. « transaction inconnue »)."""
        self._afficher(texte, ok)

    # ----------------------------------------------- lecteur actif si visible
    def showEvent(self, evenement):
        self._lecteur.demarrer()          # réserve le lecteur seulement sur cette page
        self.reinitialiser()
        super().showEvent(evenement)

    def hideEvent(self, evenement):
        self._lecteur.arreter()
        super().hideEvent(evenement)

    # ------------------------------------------------------------- interne
    def _traiter_lecture(self, numero, texte):
        """Lecture du lecteur USB (déjà ramenée dans le fil Qt par le signal)."""
        if self._occupe:
            return                        # double lecture ignorée
        if numero is None:
            self._afficher(f"Code-barres non reconnu ({texte})", ok=False)
            return
        self._champ.setText(f"{numero:06d}")
        self._transmettre(numero)

    def _touche(self, texte):
        if texte == "←":
            self._champ.backspace()
        elif texte == "OK":
            self._valider_manuel()
        elif len(self._champ.text()) < LONGUEUR_NUMERO:
            self._champ.insert(texte)

    def _valider_manuel(self):
        if self._occupe:
            return
        numero = LecteurCodeBarres.traiter_saisie(self._champ.text())
        if numero is None:
            self._afficher(f"Le numéro doit contenir {LONGUEUR_NUMERO} chiffres", ok=False)
            return
        self._transmettre(numero)

    def _transmettre(self, numero):
        self._occupe = True
        self._afficher(f"Recherche de la transaction {numero:06d}...", ok=True)
        self.numero_saisi.emit(numero)

    def _afficher(self, texte, ok):
        self._message.setText(texte)
        self._message.setStyleSheet(STYLE_OK if ok else STYLE_ERREUR)
