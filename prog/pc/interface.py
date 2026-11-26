"""Pont Qt : les échanges MQTT et SQLite restent hors du thread graphique."""

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal, pyqtSlot
from commun.t13.transport import TransportMQTT
from pc.client import ClientSupervision
from pc.demandes import JournalDemandes
from pc.fenetre import FenetreSupervision  # Réexport pour les points d’entrée existants.


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
