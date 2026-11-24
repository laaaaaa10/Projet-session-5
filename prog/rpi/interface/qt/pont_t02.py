"""Acces Qt asynchrone a T02 : aucun acces disque ou RFID dans le thread graphique.

Les methodes publiques retournent une reference de requete, jamais le resultat
synchrone du service. Le resultat arrive par reponse(reference, action, valeur).
Les API synchrones api/ restent reservees aux modules du thread de travail.
"""

from dataclasses import dataclass
import logging
from uuid import uuid4

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal, pyqtSlot

from application import integration_t03, integration_t04, integration_t13
from application.acces_comptes import AccesComptes
from application.acces_identification import AccesIdentification
from application.borne import Borne
from modeles.comptes import DemandePaiement, IdentificationCarte
from modules.gestion_comptes import ServiceComptes
from modules.lecteur_nfc_rfid import LecteurRFID
from stockage.comptes_csv import DepotComptesCSV, DOSSIER_ACTIF, JOURNAL_TECHNIQUE


@dataclass(frozen=True)
class IncidentQt:
    reference: str
    action: str
    type_erreur: str
    message: str
    fatal: bool = False


class _Signaux(QObject):
    pret = pyqtSignal(object)  # tuple[Compte, ...], apres ouverture du lecteur
    evenement_rfid = pyqtSignal(object)
    carte_lue = pyqtSignal(object)  # IdentificationCarte, hors paiement
    paiement_en_attente = pyqtSignal(object)
    resultat_paiement = pyqtSignal(object)  # observation ; ne consomme pas la file T04
    paiement_annule = pyqtSignal(str)
    reponse = pyqtSignal(str, str, object)
    erreur = pyqtSignal(object)  # IncidentQt
    avertissement = pyqtSignal(str)
    arrete = pyqtSignal()


class _AffichageSignaux:
    def __init__(self, signaux):
        self.signaux = signaux

    def evenement_rfid(self, evenement):
        self.signaux.evenement_rfid.emit(evenement)

    def compte(self, id_uart, compte):
        self.signaux.carte_lue.emit(IdentificationCarte(
            id_uart, None if compte is None else compte.solde_centimes,
        ))

    def attente_paiement(self, demande):
        self.signaux.paiement_en_attente.emit(demande)

    def resultat_paiement(self, resultat):
        self.signaux.resultat_paiement.emit(resultat)

    def annulation(self, id_transaction):
        self.signaux.paiement_annule.emit(id_transaction)


class _JournalQt(logging.Handler):
    def __init__(self, signal):
        super().__init__(logging.WARNING)
        self.signal = signal

    def emit(self, record):
        self.signal.emit(self.format(record))


class _Travailleur(_Signaux):
    def __init__(self, dossier, simulation, options, fabrique_lecteur):
        super().__init__()
        self.dossier = dossier
        self.simulation = simulation
        self.options = options
        self.fabrique_lecteur = fabrique_lecteur
        self.lecteur = self.timer = self.journal = None
        self.termine = False

    @pyqtSlot()
    def demarrer(self):
        try:
            self.journal = _JournalQt(self.avertissement)
            JOURNAL_TECHNIQUE.addHandler(self.journal)
            service = ServiceComptes(DepotComptesCSV(self.dossier))
            self.acces = AccesComptes(service)
            identification = AccesIdentification(service)
            self.t03 = integration_t03.creer_module_t03(identification)
            self.borne = Borne(service, _AffichageSignaux(self),
                               identification=identification if self.t03 is not None else None)
            self.t04 = integration_t04.creer_module_t04(self.borne)
            self.t13 = integration_t13.creer_module_t13(self.acces)
            comptes = tuple(service.lister_comptes().values())
            if self.fabrique_lecteur is not None:
                self.lecteur = self.fabrique_lecteur()
            elif self.simulation:
                from exemples.lecteur_simule import LecteurSimule
                self.lecteur = LecteurSimule()
            else:
                self.lecteur = LecteurRFID(**self.options)
            self.lecteur.ouvrir()
            self.timer = QTimer(self)
            self.timer.setTimerType(Qt.TimerType.PreciseTimer)
            self.timer.timeout.connect(self.actualiser)
            self.timer.start(2)
            self.pret.emit(comptes)
        except Exception as erreur:
            self._signaler("", "demarrage", erreur, fatal=True)
            self.fermer()

    def _signaler(self, reference, action, erreur, *, fatal=False):
        self.erreur.emit(IncidentQt(reference, action, type(erreur).__name__, str(erreur), fatal))

    def _vider_si_sans_t04(self):
        # Sans module T04, le pont est le client de demonstration. Avec T04,
        # celui-ci reste l'unique consommateur ; l'affichage observe les signaux.
        if self.t04 is None:
            self.borne.lire_resultats_paiement()

    @pyqtSlot()
    def actualiser(self):
        if self.termine:
            return
        try:
            self.borne.actualiser(self.lecteur, t03=self.t03, t04=self.t04, t13=self.t13)
            self._vider_si_sans_t04()
        except Exception as erreur:
            self._signaler("", "lecture", erreur, fatal=True)
            self.fermer()

    @pyqtSlot(str, str, object)
    def commander(self, reference, action, arguments):
        if self.termine:
            return
        try:
            comptes = {"consulter_solde", "lister_soldes", "ajouter_credit", "retrouver_resultat_credit"}
            paiements = {"demander_paiement", "retrouver_resultat_paiement", "annuler_paiement"}
            if action in comptes:
                resultat = getattr(self.acces, action)(*arguments)
            elif action in paiements:
                resultat = getattr(self.borne, action)(*arguments)
            elif action == "simuler_badge" and self.simulation:
                resultat = self.lecteur.simuler(*arguments)
            else:
                raise ValueError("Commande indisponible : " + action)
            self._vider_si_sans_t04()
            self.reponse.emit(reference, action, resultat)
        except Exception as erreur:
            self._signaler(reference, action, erreur)

    @pyqtSlot()
    def fermer(self):
        if self.termine:
            return
        self.termine = True
        if self.timer is not None:
            self.timer.stop()
        try:
            if self.lecteur is not None:
                self.lecteur.fermer()
        except Exception as erreur:
            self._signaler("", "fermeture", erreur, fatal=True)
        finally:
            if self.journal is not None:
                JOURNAL_TECHNIQUE.removeHandler(self.journal)
                self.journal.close()
            self.arrete.emit()


class PontT02Qt(_Signaux):
    """Objet a posseder dans l'UI jusqu'a arrete ; une instance = un lecteur.

    Appeler demarrer() apres connexion des signaux et attendre pret avant les
    commandes. arreter() est asynchrone : la fenetre attend arrete pour fermer.
    Les fabriques integration_t03/t04/t13 construisent ici des modules de travail,
    jamais des QWidget. Les pages Qt sont creees separement dans le thread GUI.
    """

    _requete = pyqtSignal(str, str, object)
    _arret_demande = pyqtSignal()

    def __init__(self, dossier_donnees=DOSSIER_ACTIF, *, simulation=False,
                 options_lecteur=None, fabrique_lecteur=None, parent=None):
        super().__init__(parent)
        self.dossier = dossier_donnees
        self.simulation = simulation
        self.options = dict(options_lecteur or {})
        self.fabrique_lecteur = fabrique_lecteur
        self._thread = self._travailleur = None
        self._accepte_commandes = False
        self._arret_en_cours = False

    @property
    def en_cours(self) -> bool:
        return self._thread is not None

    def demarrer(self) -> None:
        if self.en_cours:
            raise RuntimeError("Le pont T02 est deja demarre")
        self._arret_en_cours = False
        thread = self._thread = QThread(self)
        travailleur = self._travailleur = _Travailleur(
            self.dossier, self.simulation, self.options, self.fabrique_lecteur,
        )
        travailleur.moveToThread(thread)
        thread.started.connect(travailleur.demarrer)
        self._requete.connect(travailleur.commander, Qt.ConnectionType.QueuedConnection)
        self._arret_demande.connect(travailleur.fermer, Qt.ConnectionType.QueuedConnection)
        travailleur.pret.connect(self._pret, Qt.ConnectionType.QueuedConnection)
        travailleur.erreur.connect(self._erreur, Qt.ConnectionType.QueuedConnection)
        for nom in ("evenement_rfid", "carte_lue", "paiement_en_attente",
                    "resultat_paiement", "paiement_annule", "reponse", "avertissement"):
            getattr(travailleur, nom).connect(getattr(self, nom), Qt.ConnectionType.QueuedConnection)
        travailleur.arrete.connect(thread.quit)
        travailleur.arrete.connect(travailleur.deleteLater)
        thread.finished.connect(self._termine)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @pyqtSlot(object)
    def _pret(self, comptes):
        if self._arret_en_cours:
            return
        self._accepte_commandes = True
        self.pret.emit(comptes)

    @pyqtSlot(object)
    def _erreur(self, incident):
        if incident.fatal:
            self._accepte_commandes = False
        self.erreur.emit(incident)

    @pyqtSlot()
    def _termine(self):
        self._accepte_commandes = False
        self._thread = self._travailleur = None
        self.arrete.emit()

    def arreter(self) -> None:
        if self.en_cours:
            self._arret_en_cours = True
            self._accepte_commandes = False
            self._arret_demande.emit()

    def _envoyer(self, action, *arguments):
        if not self._accepte_commandes:
            raise RuntimeError("Attendre le signal pret ; aucune commande pendant l'arret")
        reference = uuid4().hex
        self._requete.emit(reference, action, arguments)
        return reference

    def consulter_solde(self, id_uart: str) -> str:
        return self._envoyer("consulter_solde", id_uart)

    def lister_soldes(self) -> str:
        return self._envoyer("lister_soldes")

    def ajouter_credit(self, id_transaction: str, id_uart: str, montant_centimes: int) -> str:
        return self._envoyer("ajouter_credit", id_transaction, id_uart, montant_centimes)

    def retrouver_resultat_credit(self, id_transaction: str) -> str:
        return self._envoyer("retrouver_resultat_credit", id_transaction)

    def demander_paiement(self, demande: DemandePaiement) -> str:
        return self._envoyer("demander_paiement", demande)

    def retrouver_resultat_paiement(self, id_transaction: str) -> str:
        return self._envoyer("retrouver_resultat_paiement", id_transaction)

    def annuler_paiement(self, id_transaction: str) -> str:
        return self._envoyer("annuler_paiement", id_transaction)

    def simuler_badge(self, id_uart: str) -> str:
        return self._envoyer("simuler_badge", id_uart)
