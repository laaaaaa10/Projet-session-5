"""Raccordement service/MQTT, journal durable et fenetre Qt de diagnostic."""

import os
from pathlib import Path
import sys
import unittest

PROG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROG))
sys.path.insert(0, str(PROG / "rpi"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import test_t13_mqtt as banc
from test_comptes_transactions import BancComptes
from exemples.systeme_t13_simule import SystemeT13Simule
from modules.service_t13 import GestionServiceT13
from modules.supervision import SupervisionT13


class TestsRaccordementService(BancComptes):
    tour = banc.TestsT13.tour
    injecter = banc.TestsT13.injecter

    def setUp(self):
        super().setUp()
        self.horloge = banc.Horloge()
        self.pi, self.pc = banc.TransportSimule(), banc.TransportSimule()
        self.pi.pair, self.pc.pair = self.pc, self.pi
        self.simule = SystemeT13Simule(horloge=self.horloge)
        self.gestion = GestionServiceT13(self.simule, self.racine / "service.sqlite3", horloge=self.horloge)
        self.supervision = SupervisionT13(banc.AccesComptes(self.service), self.pi,
                                         service=self.gestion, horloge=self.horloge)
        self.addCleanup(self.supervision.fermer)
        self.journal = banc.JournalDemandes(self.racine / "pc.sqlite3", "essai")
        self.client = banc.ClientSupervision(self.pc, self.journal, horloge=self.horloge)
        self.addCleanup(self.client.fermer)
        self.tour()

    def test_quatre_commandes_correlées_et_etats_distincts(self):
        self.assertTrue(self.client.etat["service_simule"])
        self.assertTrue(self.client.etat["disponibilite"]["service"])
        for commande, etat in (("REMETTRE_EN_SERVICE", "EN_SERVICE"),
                               ("METTRE_HORS_SERVICE", "HORS_SERVICE"),
                               ("ARRET_IMMEDIAT", "ARRET_VERROUILLE")):
            identifiant = self.client.demander(commande)
            self.tour()
            self.assertEqual(self.journal.historique()[0]["reponse"]["id_commande"], identifiant)
            self.assertEqual(self.client.etat["etat_service"], etat)
        self.simule.injecter("intervention")
        identifiant = self.client.demander("REINITIALISER")
        self.tour()
        self.assertEqual(self.journal.historique()[0]["reponse"]["phase"], "ACCEPTEE")
        self.assertEqual(len(self.journal.en_attente()), 1)
        self.horloge.temps += 1
        self.tour()
        self.assertEqual(self.client.etat["etat_service"], "HORS_SERVICE")
        self.assertEqual(self.journal.en_attente(), [])
        self.assertEqual(self.journal.historique()[0]["reponse"]["id_commande"], identifiant)

    def test_progression_hors_ligne_et_reponse_finale_retrouvee(self):
        self.client.demander("REMETTRE_EN_SERVICE")
        self.tour()
        self.simule.injecter("retrait")
        identifiant = self.client.demander("METTRE_HORS_SERVICE")
        self.tour()
        self.assertEqual(self.client.etat["etat_service"], "MISE_HORS_SERVICE")
        self.pi.etat = self.pc.etat = (False, 1, "coupure")
        self.simule.injecter("fin-sequence")
        self.tour()
        self.assertEqual(self.gestion.etat, "MISE_HORS_SERVICE")
        self.simule.injecter("retirer-vehicule")
        self.tour()
        self.assertEqual(self.gestion.etat, "HORS_SERVICE")
        self.pi.etat = self.pc.etat = (True, 2, "")
        self.horloge.temps += 4
        self.tour()
        self.tour()
        self.assertEqual(self.client.etat["etat_service"], "HORS_SERVICE")
        resultat = self.journal.historique()[0]["reponse"]
        self.assertEqual(resultat["id_commande"], identifiant)
        self.assertEqual(resultat["phase"], "TERMINEE")
        self.assertTrue(resultat["donnees"]["deja_traitee"])

    def test_arret_retenu_interdit_et_repetition_normale_idempotente(self):
        demande = banc.nouvelle_commande("ARRET_IMMEDIAT")
        self.assertEqual(self.injecter(demande, retenu=True)[-1]["code"], "MESSAGE_INVALIDE")
        self.assertEqual(self.gestion.etat, "HORS_SERVICE")
        self.injecter(demande)
        self.injecter(demande)
        self.assertEqual(self.simule.arrets, 1)
        self.assertTrue(self.client.etat["disponibilite"]["service"])
        self.assertTrue(all(p["logique"] == "INCONNU" for p in self.supervision.instantane()["places"]))
        self.assertIsNone(self.supervision.instantane()["transactions"])


try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QObject, pyqtSignal
    from pc.interface import FenetreSupervision
    QT = True
except ModuleNotFoundError as erreur:
    if erreur.name != "PyQt6":
        raise
    QT = False

if QT:
    class PontSimule(QObject):
        vue = pyqtSignal(object)
        erreur = pyqtSignal(str)
        termine = pyqtSignal()
        requete = pyqtSignal(str, object)
        arret = pyqtSignal()


@unittest.skipUnless(QT, "PyQt6 absent : pas de validation graphique")
class TestsBoutonsService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_commandes_simulees_visibles_et_desactivees_sur_perte_ou_arret(self):
        pont = PontSimule()
        fenetre = FenetreSupervision(pont)
        pont.arret.connect(pont.termine.emit)
        self.addCleanup(fenetre.close)
        requetes = []
        pont.requete.connect(lambda action, params: requetes.append((action, params)))
        vue = {"statut": "A_JOUR", "demandes": [], "etat": {
            "etat_service": "HORS_SERVICE", "service_simule": True,
            "diagnostic_service": {}, "disponibilite": {"service": True}}}
        fenetre.actualiser(vue)
        self.assertFalse(fenetre.simulation.isHidden())
        for action, bouton in fenetre.commandes_service.items():
            self.assertTrue(bouton.isEnabled())
            bouton.click()
            self.assertEqual(requetes[-1], (action, {}))
        for statut in ("PERIMEES", "DECONNECTE"):
            fenetre.actualiser(dict(vue, statut=statut))
            self.assertTrue(all(not b.isEnabled() for b in fenetre.commandes_service.values()))
        fenetre.actualiser(vue)
        pont.termine.emit()
        self.assertTrue(all(not b.isEnabled() for b in fenetre.commandes_service.values()))
        fenetre.actualiser(vue)
        self.assertTrue(all(not b.isEnabled() for b in fenetre.commandes_service.values()))


if __name__ == "__main__":
    unittest.main()
