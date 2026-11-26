"""Fenetre PC et travailleur Qt. Les echanges MQTT et SQLite restent hors GUI."""

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from commun.t13.protocole import ACTIONS_SERVICE
from commun.t13.transport import TransportMQTT
from pc.client import ClientSupervision
from pc.demandes import JournalDemandes


class TravailleurPC(QObject):
    vue = pyqtSignal(object)
    erreur = pyqtSignal(str)
    termine = pyqtSignal()

    def __init__(self, config, journal):
        super().__init__()
        self.config, self.chemin = config, journal
        self.client = self.timer = None
        self._ferme = False

    @pyqtSlot()
    def demarrer(self):
        try:
            transport = TransportMQTT(self.config, "pc")
            cible = f"{self.config.hote}:{self.config.port}/{self.config.prefixe}"
            journal = JournalDemandes(self.chemin, cible)
            self.client = ClientSupervision(transport, journal)
            transport.demarrer()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.actualiser)
            self.timer.start(100)
            self.actualiser()
        except Exception as erreur:
            self.erreur.emit(str(erreur))
            self.fermer()

    @pyqtSlot()
    def actualiser(self):
        try:
            self.client.actualiser()
            self.vue.emit(self.client.vue())
        except Exception as erreur:
            self.erreur.emit(str(erreur))
            self.fermer()

    @pyqtSlot(str, object)
    def demander(self, action, parametres):
        if self._ferme or self.client is None:
            return
        try:
            if action == "REPRENDRE_DEMANDE":
                self.client.reprendre(parametres["id_commande"])
            else:
                self.client.demander(action, **parametres)
            self.actualiser()
        except Exception as erreur:
            self.erreur.emit(str(erreur))

    @pyqtSlot()
    def fermer(self):
        if self._ferme:
            return
        self._ferme = True
        if self.timer is not None:
            self.timer.stop()
        try:
            if self.client is not None:
                self.client.fermer()
        finally:
            self.termine.emit()


class PontPC(QObject):
    vue = pyqtSignal(object)
    erreur = pyqtSignal(str)
    termine = pyqtSignal()
    requete = pyqtSignal(str, object)
    arret = pyqtSignal()

    def __init__(self, config, journal, parent=None):
        super().__init__(parent)
        self.thread = QThread(self)
        self.travailleur = TravailleurPC(config, journal)
        self.travailleur.moveToThread(self.thread)
        self.thread.started.connect(self.travailleur.demarrer)
        self.requete.connect(self.travailleur.demander, Qt.ConnectionType.QueuedConnection)
        self.arret.connect(self.travailleur.fermer, Qt.ConnectionType.QueuedConnection)
        self.travailleur.vue.connect(self.vue, Qt.ConnectionType.QueuedConnection)
        self.travailleur.erreur.connect(self.erreur, Qt.ConnectionType.QueuedConnection)
        self.travailleur.termine.connect(self.thread.quit)
        self.travailleur.termine.connect(self.travailleur.deleteLater)
        self.thread.finished.connect(self.termine)


class FenetreSupervision(QMainWindow):
    def __init__(self, pont):
        super().__init__()
        self.pont = pont
        self._fermeture = self._termine = False
        self._selection = None
        self._donnees_fraiches = False
        self.setWindowTitle("ESA — Supervision PC · T13")
        self.resize(1040, 800)
        contenu = QWidget()
        self.setCentralWidget(contenu)
        disposition = QVBoxLayout(contenu)
        titre = QLabel("Supervision ESA")
        titre.setStyleSheet("font-size: 26px; font-weight: bold;")
        disposition.addWidget(titre)
        self.connexion = QLabel("Connexion en cours — données indisponibles")
        self.connexion.setStyleSheet("padding: 10px; background: #ffe4a6; color: #392b00;")
        disposition.addWidget(self.connexion)
        self.simulation = QLabel("SIMULATION T03/T11/T12 et sécurité CAN — aucun moteur commandé")
        self.simulation.setStyleSheet("padding: 8px; background: #ffdf8a; color: #302200; font-weight: bold;")
        self.simulation.setVisible(False)
        disposition.addWidget(self.simulation)
        self.service = QLabel("État du système : INCONNU")
        disposition.addWidget(self.service)
        places = QGroupBox("Les 14 places")
        grille = QGridLayout(places)
        self.places = {}
        for niveau in (1, 2):
            for place in range(1, 8):
                identifiant = f"E{niveau}.{place}"
                label = QLabel(f"{identifiant}\nINCONNU")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setStyleSheet("padding: 12px; border: 1px solid #999;")
                self.places[identifiant] = label
                grille.addWidget(label, niveau - 1, place - 1)
        disposition.addWidget(places)
        ligne = QHBoxLayout()
        self.comptes = QTableWidget(0, 2)
        self.comptes.setHorizontalHeaderLabels(["ID UART", "Solde courant (¢)"])
        self.comptes.setColumnWidth(0, 170)
        self.comptes.horizontalHeader().setStretchLastSection(True)
        self.comptes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        ligne.addWidget(self.comptes)
        actions = QVBoxLayout()
        self.carte = QLineEdit()
        self.carte.setPlaceholderText("ID UART complet — 10 caractères")
        self.carte.setMaxLength(10)
        actions.addWidget(self.carte)
        self.montant = QSpinBox()
        self.montant.setRange(1, 2_147_483_647)
        self.montant.setValue(500)
        self.montant.setSuffix(" centimes")
        actions.addWidget(self.montant)
        self.consulter = QPushButton("Consulter le solde")
        self.crediter = QPushButton("Ajouter ce crédit")
        self.consulter.clicked.connect(lambda: self._demander("CONSULTER_SOLDE"))
        self.crediter.clicked.connect(lambda: self._demander("AJOUTER_CREDIT"))
        actions.addWidget(self.consulter)
        actions.addWidget(self.crediter)
        actions.addStretch()
        ligne.addLayout(actions)
        disposition.addLayout(ligne)
        commandes = QHBoxLayout()
        self.commandes_service = {}
        for action in sorted(ACTIONS_SERVICE):
            bouton = QPushButton(action.replace("_", " "))
            bouton.setEnabled(False)
            bouton.setToolTip("Nécessite une gestion de service raccordée et des données à jour")
            bouton.clicked.connect(lambda checked=False, action=action: self._demander_service(action))
            self.commandes_service[action] = bouton
            commandes.addWidget(bouton)
        disposition.addLayout(commandes)
        self.informations = QTextEdit()
        self.informations.setReadOnly(True)
        self.informations.setMaximumHeight(120)
        disposition.addWidget(self.informations)
        disposition.addWidget(QLabel("Demandes PC et réponses du Pi — une acceptation n'est pas une fin d'action"))
        self.demandes = QTableWidget(0, 3)
        self.demandes.setHorizontalHeaderLabels(["ID durable", "Commande", "Réponse"])
        self.demandes.setColumnWidth(0, 360)
        self.demandes.setColumnWidth(1, 180)
        self.demandes.horizontalHeader().setStretchLastSection(True)
        self.demandes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.demandes.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.demandes.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.demandes.itemSelectionChanged.connect(self._selectionner)
        disposition.addWidget(self.demandes)
        self.reprendre = QPushButton("Renvoyer la demande sélectionnée avec le même ID")
        self.reprendre.setToolTip("Sélectionner une ligne dans le tableau des demandes ; les données du Pi doivent être à jour.")
        self.reprendre.setEnabled(False)
        self.reprendre.clicked.connect(self._reprendre)
        disposition.addWidget(self.reprendre)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        disposition.addWidget(self.message)
        self.consulter.setEnabled(False)
        self.crediter.setEnabled(False)
        pont.vue.connect(self.actualiser)
        pont.erreur.connect(self.message.setText)
        pont.termine.connect(self._arrete)

    def _demander(self, action):
        self.message.clear()
        self.crediter.setEnabled(False)
        params = {"id_uart": self.carte.text().strip().upper()}
        if action == "AJOUTER_CREDIT":
            params["montant_centimes"] = self.montant.value()
        self.pont.requete.emit(action, params)

    def _demander_service(self, action):
        if self.commandes_service[action].isEnabled():
            self.message.clear()
            self.pont.requete.emit(action, {})

    def _selectionner(self):
        # L'index courant et les lignes selectionnees sont distincts dans Qt.
        lignes = self.demandes.selectionModel().selectedRows(0)
        self._selection = lignes[0].data() if len(lignes) == 1 else None
        self._actualiser_reprise()

    def _actualiser_reprise(self):
        self.reprendre.setEnabled(self._donnees_fraiches and self._selection is not None
                                  and not self._fermeture and not self._termine)

    def _reprendre(self):
        if self.reprendre.isEnabled() and self._selection:
            self.pont.requete.emit("REPRENDRE_DEMANDE", {"id_commande": self._selection})

    @pyqtSlot(object)
    def actualiser(self, vue):
        frais = vue["statut"] == "A_JOUR"
        self._donnees_fraiches = frais
        self.connexion.setText({"A_JOUR": "PC ↔ broker MQTT ↔ Pi — données à jour",
                               "PERIMEES": "Broker connecté — données périmées, attente du Pi",
                               "DECONNECTE": "Déconnecté — données périmées"}[vue["statut"]])
        self.connexion.setStyleSheet("padding: 10px; color: #182018; background: " +
                                    ("#c7e8cb;" if frais else "#ffe4a6;"))
        etat = vue["etat"] or {}
        self.simulation.setVisible(etat.get("service_simule") is True)
        self.service.setText("État du système : " + etat.get("etat_service", "INCONNU"))
        service_disponible = (frais and etat.get("disponibilite", {}).get("service", False)
                             and not self._fermeture and not self._termine)
        for bouton in self.commandes_service.values():
            bouton.setEnabled(service_disponible)
        for place in etat.get("places", []):
            self.places[place["id"]].setText(place["id"] + "\n" + place["logique"])
        soldes = etat.get("soldes") or {}
        self.comptes.setRowCount(len(soldes))
        for ligne, (carte, solde) in enumerate(sorted(soldes.items())):
            self.comptes.setItem(ligne, 0, QTableWidgetItem(carte))
            self.comptes.setItem(ligne, 1, QTableWidgetItem(str(solde)))
        disponible = frais and etat.get("disponibilite", {}).get("T02", False)
        self.consulter.setEnabled(disponible and not self._fermeture)
        attente = any(not d["termine"] and d["demande"]["commande"] == "AJOUTER_CREDIT"
                      for d in vue["demandes"])
        self.crediter.setEnabled(disponible and not attente and not self._fermeture)
        self.informations.setPlainText("\n".join([
            *(["Service simulé : " + str(etat["diagnostic_service"])] if etat.get("service_simule") else []),
            "Transactions : indisponibles" if etat.get("transactions") is None else str(etat["transactions"]),
            "Statistiques : indisponibles" if etat.get("statistiques") is None else str(etat["statistiques"]),
            *[str(a.get("message", a)) if isinstance(a, dict) else str(a) for a in etat.get("anomalies", [])],
        ]))
        self.demandes.blockSignals(True)
        self.demandes.setRowCount(len(vue["demandes"]))
        ligne_selection = None
        for ligne, entree in enumerate(vue["demandes"]):
            demande, resultat = entree["demande"], entree["reponse"]
            texte = "EN ATTENTE" if resultat is None else f"{resultat['phase']} · {resultat['code']}"
            if resultat and resultat["code"] == "SOLDE":
                texte += f" · {resultat['donnees'].get('solde_centimes')} ¢"
            if resultat and resultat["donnees"].get("recu", {}).get("deja_traitee"):
                texte += " · déjà traitée"
            details = str(resultat["donnees"]) if resultat else ""
            for colonne, valeur in enumerate((demande["id_commande"], demande["commande"], texte)):
                # Garder les cellules existantes pendant les rafraichissements
                # periodiques, y compris pendant un clic de l'utilisateur.
                item = self.demandes.item(ligne, colonne)
                if item is None:
                    item = QTableWidgetItem(valeur)
                    self.demandes.setItem(ligne, colonne, item)
                elif item.text() != valeur:
                    item.setText(valeur)
                if item.toolTip() != details:
                    item.setToolTip(details)
            if demande["id_commande"] == self._selection:
                ligne_selection = ligne
        if ligne_selection is not None:
            selection = self.demandes.selectionModel().selectedRows()
            if [index.row() for index in selection] != [ligne_selection]:
                self.demandes.selectRow(ligne_selection)
        else:
            self.demandes.clearSelection()
            self._selection = None
        self.demandes.blockSignals(False)
        self._actualiser_reprise()

    def closeEvent(self, evenement):
        if self._termine:
            evenement.accept()
            return
        evenement.ignore()
        if not self._fermeture:
            self._fermeture = True
            self.centralWidget().setEnabled(False)
            self.message.setText("Fermeture du client MQTT…")
            self.pont.arret.emit()

    def _arrete(self):
        self._termine = True
        self._donnees_fraiches = False
        if self._fermeture:
            self.close()
        else:
            self.connexion.setText("Application arrêtée — données périmées")
            self.consulter.setEnabled(False)
            self.crediter.setEnabled(False)
            self.reprendre.setEnabled(False)
            for bouton in self.commandes_service.values():
                bouton.setEnabled(False)
