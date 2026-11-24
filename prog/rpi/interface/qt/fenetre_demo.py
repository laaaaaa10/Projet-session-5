"""Banc graphique T02 ; aucun tarif, reservation ou parcours T03/T04 implemente."""

from uuid import uuid4

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from modeles.comptes import DemandePaiement, afficher_montant
from modules.lecteur_nfc_rfid import numero_badge


class FenetreDemoT02(QMainWindow):
    def __init__(self, pont, *, donnees_temporaires=True):
        super().__init__()
        self.pont = pont
        self._prete = self._fermeture = self._arret_termine = False
        self._attente = self._derniere_demande = self._dernier_credit = None
        self._envoi_paiement = self._envoi_credit = False
        self._reprise_paiement = self._reprise_credit = False
        self._comptes = {}
        self.setWindowTitle("ESA — Banc graphique T02")
        self.resize(960, 740)
        self.setMinimumSize(640, 440)
        self.setStyleSheet("""
            QMainWindow, QScrollArea, QWidget#contenu { background: #f3f5f8; }
            QLabel { color: #1b2d43; }
            QLabel#titre { font-size: 25px; font-weight: 700; }
            QLabel#mode { color: #166958; font-weight: 700; }
            QGroupBox { background: white; border: 1px solid #d9e0e9;
                border-radius: 8px; margin-top: 14px; padding: 16px 12px 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px;
                color: #1b2d43; font-weight: 600; }
            QPushButton { padding: 10px 12px; border-radius: 5px;
                background: #173a5e; color: white; border: none; }
            QPushButton:disabled { background: #dfe5ec; color: #718096; }
            QPushButton:hover:enabled { background: #225987; }
            QSpinBox, QComboBox { padding: 8px; background: white; color: #1b2d43; }
            QTableWidget, QPlainTextEdit { background: white; color: #1b2d43;
                border: 1px solid #d9e0e9; border-radius: 4px; }
        """)
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        contenu = QWidget()
        contenu.setObjectName("contenu")
        zone.setWidget(contenu)
        self.setCentralWidget(zone)
        page = QVBoxLayout(contenu)
        page.setContentsMargins(22, 18, 22, 18)
        entete = QHBoxLayout()
        titre = QLabel("T02 · Comptes et cartes")
        titre.setObjectName("titre")
        entete.addWidget(titre)
        entete.addStretch()
        mode = QLabel("SIMULATION PC" if pont.simulation else "LECTEUR RÉEL")
        mode.setObjectName("mode")
        entete.addWidget(mode)
        page.addLayout(entete)
        page.addWidget(QLabel("Démonstration · Données temporaires supprimées à la fermeture"
                              if donnees_temporaires else "Démonstration · Données persistantes dans le dossier choisi"))
        self.message = QLabel("Ouverture du service et du lecteur…")
        self.message.setWordWrap(True)
        self.message.setMinimumHeight(46)
        page.addWidget(self.message)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Compte", "Numéro du badge", "Solde courant"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFixedHeight(108)
        page.addWidget(self.table)
        self.badges = []
        if pont.simulation:
            ligne = QHBoxLayout()
            for texte, id_uart in (("Présenter Jason", "11008827F9"),
                                    ("Présenter Lucia", "1100823734"),
                                    ("Carte inconnue", "1100880F2D")):
                bouton = QPushButton(texte)
                bouton.clicked.connect(lambda checked=False, carte=id_uart: pont.simuler_badge(carte))
                ligne.addWidget(bouton)
                self.badges.append(bouton)
            page.addLayout(ligne)
        else:
            page.addWidget(QLabel("Présentez un badge au lecteur. Une lecture seule consulte le compte."))
        panneaux = QGridLayout()
        paiement = QGroupBox("Paiement de test — montant fourni à T02")
        p = QVBoxLayout(paiement)
        self.montant_paiement = self._montant(500, 0)
        p.addWidget(QLabel("Montant en centimes (500 = 5,00 $)"))
        p.addWidget(self.montant_paiement)
        self.preparer = QPushButton("Préparer un paiement")
        self.preparer.clicked.connect(self._nouveau_paiement)
        p.addWidget(self.preparer)
        ligne = QHBoxLayout()
        self.annuler = QPushButton("Annuler l’attente")
        self.annuler.clicked.connect(self._annuler)
        self.rejouer_paiement = QPushButton("Rejouer le même ID")
        self.rejouer_paiement.clicked.connect(self._repeter_paiement)
        ligne.addWidget(self.annuler)
        ligne.addWidget(self.rejouer_paiement)
        p.addLayout(ligne)
        self.etat_paiement = QLabel("Aucun paiement en attente.")
        self.etat_paiement.setWordWrap(True)
        p.addWidget(self.etat_paiement)
        credit = QGroupBox("Crédit de test — accès T13")
        c = QVBoxLayout(credit)
        self.carte_credit = QComboBox()
        c.addWidget(self.carte_credit)
        c.addWidget(QLabel("Montant en centimes"))
        self.montant_credit = self._montant(500, 1)
        c.addWidget(self.montant_credit)
        self.crediter = QPushButton("Ajouter le crédit")
        self.crediter.clicked.connect(self._nouveau_credit)
        self.rejouer_credit = QPushButton("Rejouer le même ID")
        self.rejouer_credit.clicked.connect(self._repeter_credit)
        c.addWidget(self.crediter)
        c.addWidget(self.rejouer_credit)
        panneaux.addWidget(paiement, 0, 0)
        panneaux.addWidget(credit, 0, 1)
        page.addLayout(panneaux)
        self.reference = QLabel("Les références d’opération apparaîtront ici.")
        self.reference.setWordWrap(True)
        self.reference.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        page.addWidget(self.reference)
        self.journal = QPlainTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setMaximumBlockCount(300)
        self.journal.setFixedHeight(100)
        self.journal.setPlaceholderText("Journal de la démonstration")
        page.addWidget(self.journal)
        pied = QHBoxLayout()
        self.actualiser = QPushButton("Actualiser les soldes")
        self.actualiser.clicked.connect(pont.lister_soldes)
        self.relancer = QPushButton("Relancer la connexion")
        self.relancer.clicked.connect(self.demarrer)
        quitter = QPushButton("Fermer")
        quitter.clicked.connect(self.close)
        pied.addWidget(self.actualiser)
        pied.addWidget(self.relancer)
        pied.addStretch()
        pied.addWidget(quitter)
        page.addLayout(pied)
        pont.pret.connect(self._pret)
        pont.carte_lue.connect(self._carte_lue)
        pont.paiement_en_attente.connect(self._paiement_attendu)
        pont.resultat_paiement.connect(self._resultat_paiement)
        pont.paiement_annule.connect(self._paiement_annule)
        pont.reponse.connect(self._reponse)
        pont.erreur.connect(self._erreur)
        pont.evenement_rfid.connect(lambda evt: self.journal.appendPlainText(str(evt)))
        pont.avertissement.connect(self._avertissement)
        pont.arrete.connect(self._arrete)
        self._boutons()

    @staticmethod
    def _montant(valeur, minimum):
        entree = QSpinBox()
        entree.setRange(minimum, 1_000_000)
        entree.setSingleStep(100)
        entree.setValue(valeur)
        return entree

    def demarrer(self):
        if not self.pont.en_cours and not self._fermeture:
            self._arret_termine = False
            self._attente = None
            self.etat_paiement.setText("Aucun paiement en attente.")
            self.message.setText("Ouverture du service et du lecteur…")
            self.pont.demarrer()
            self._boutons()

    def _boutons(self):
        disponible = self._prete and not self._fermeture
        self.preparer.setEnabled(disponible and self._attente is None and
                                 not self._envoi_paiement and not self._reprise_paiement)
        self.annuler.setEnabled(disponible and self._attente is not None)
        self.rejouer_paiement.setEnabled(disponible and self._derniere_demande is not None and
                                         not self._envoi_paiement)
        self.crediter.setEnabled(disponible and not self._envoi_credit and not self._reprise_credit)
        self.rejouer_credit.setEnabled(disponible and self._dernier_credit is not None and not self._envoi_credit)
        self.actualiser.setEnabled(disponible)
        self.relancer.setEnabled(not self.pont.en_cours and not self._fermeture)
        for bouton in self.badges:
            bouton.setEnabled(disponible)

    @pyqtSlot(object)
    def _pret(self, comptes):
        self._prete = True
        self._comptes = {c.id_uart: c for c in comptes}
        self.table.setRowCount(len(comptes))
        self.carte_credit.clear()
        for ligne, compte in enumerate(comptes):
            for colonne, texte in enumerate((compte.nom, numero_badge(compte.id_uart), compte.solde_affiche)):
                element = QTableWidgetItem(texte)
                element.setToolTip("ID UART : " + compte.id_uart)
                self.table.setItem(ligne, colonne, element)
            self.carte_credit.addItem(compte.nom, compte.id_uart)
        self.message.setText("Prêt. Présentez une carte pour consulter son compte.")
        self._boutons()

    @pyqtSlot(object)
    def _carte_lue(self, lecture):
        compte = self._comptes.get(lecture.id_uart)
        self.message.setText(
            f"Compte reconnu · {compte.nom if compte else lecture.id_uart} · {afficher_montant(lecture.solde_centimes)}"
            if lecture.compte_connu else f"Carte refusée · {numero_badge(lecture.id_uart)} · compte inconnu"
        )
        if self._prete and not self._fermeture:
            self.pont.lister_soldes()

    def _nouveau_paiement(self):
        self._derniere_demande = DemandePaiement("qt:p:" + uuid4().hex, self.montant_paiement.value())
        self._repeter_paiement()

    def _repeter_paiement(self):
        self._envoi_paiement = True
        self.reference.setText("Paiement : " + self._derniere_demande.id_transaction)
        self.pont.demander_paiement(self._derniere_demande)
        self._boutons()

    @pyqtSlot(object)
    def _paiement_attendu(self, demande):
        self._attente = demande
        self.etat_paiement.setText(f"À payer : {afficher_montant(demande.montant_centimes)} · présentez une carte.")
        self._boutons()

    def _annuler(self):
        self.pont.annuler_paiement(self._attente.id_transaction)

    @pyqtSlot(str)
    def _paiement_annule(self, identifiant):
        if self._attente is not None and self._attente.id_transaction == identifiant:
            self._attente = None
            self.etat_paiement.setText("Attente annulée. Aucun remboursement effectué.")
        self._boutons()

    @pyqtSlot(object)
    def _resultat_paiement(self, resultat):
        if self._attente is not None and self._attente.id_transaction == resultat.id_transaction:
            self._attente = None
            self.etat_paiement.setText("Aucun paiement en attente.")
        if self._derniere_demande is not None and self._derniere_demande.id_transaction == resultat.id_transaction:
            self._reprise_paiement = False
        self._afficher_resultat(resultat)
        self._boutons()

    def _nouveau_credit(self):
        self._dernier_credit = ("qt:c:" + uuid4().hex, self.carte_credit.currentData(), self.montant_credit.value())
        self._repeter_credit()

    def _repeter_credit(self):
        self._envoi_credit = True
        self.reference.setText("Crédit : " + self._dernier_credit[0])
        self.pont.ajouter_credit(*self._dernier_credit)
        self._boutons()

    def _afficher_resultat(self, resultat):
        texte = f"{resultat.statut.value} · {afficher_montant(resultat.montant_centimes)}"
        if resultat.deja_traitee:
            texte += " · résultat déjà enregistré, aucun nouveau mouvement"
        self.message.setText(texte)
        self.journal.appendPlainText(resultat.id_transaction + " | " + texte)
        if self._prete and not self._fermeture:
            self.pont.lister_soldes()

    @pyqtSlot(str, str, object)
    def _reponse(self, reference, action, valeur):
        if action == "lister_soldes":
            for ligne, id_uart in enumerate(self._comptes):
                if id_uart in valeur:
                    self.table.item(ligne, 2).setText(afficher_montant(valeur[id_uart]))
        elif action == "ajouter_credit":
            self._envoi_credit = self._reprise_credit = False
            self._afficher_resultat(valeur)
        elif action == "demander_paiement":
            self._envoi_paiement = False
        self._boutons()

    @pyqtSlot(object)
    def _erreur(self, incident):
        self.journal.appendPlainText(f"ERREUR {incident.type_erreur} | {incident.action} | {incident.message}")
        self.message.setText(f"Erreur : {incident.message}")
        if incident.type_erreur == "ErreurStockage":
            if incident.action == "ajouter_credit":
                self._reprise_credit = True
            if incident.action in ("demander_paiement", "annuler_paiement", "lecture"):
                self._reprise_paiement = self._derniere_demande is not None
        if incident.fatal:
            self._prete = False
            if self._attente is not None or self._envoi_paiement:
                self._reprise_paiement = True
            if self._envoi_credit:
                self._reprise_credit = True
        if incident.fatal or incident.action == "ajouter_credit":
            self._envoi_credit = False
        if incident.fatal or incident.action == "demander_paiement":
            self._envoi_paiement = False
        self._boutons()

    @pyqtSlot(str)
    def _avertissement(self, message):
        self.journal.appendPlainText(message)

    @pyqtSlot()
    def _arrete(self):
        self._prete = False
        self._arret_termine = True
        self._boutons()
        if self._fermeture:
            self.close()

    def closeEvent(self, evenement):
        if self.pont.en_cours and not self._arret_termine:
            evenement.ignore()
            self._fermeture = True
            self.message.setText("Fermeture : fin de l’opération en cours et libération du lecteur…")
            self._boutons()
            self.pont.arreter()
        else:
            evenement.accept()
