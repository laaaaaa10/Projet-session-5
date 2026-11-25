"""Tests reseau reels sur un broker local ; aucun Raspberry Pi ni Wi-Fi physique."""

import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

PROG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROG))
sys.path.insert(0, str(PROG / "rpi"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from application.acces_comptes import AccesComptes
from commun.t13.configuration import ConfigurationMQTT
from commun.t13.transport import TransportMQTT
from modules.supervision import SupervisionT13
from pc.client import ClientSupervision
from pc.demandes import JournalDemandes
from banc_broker_t13 import BancBroker
from test_comptes_transactions import BancComptes, JASON


@unittest.skipUnless(os.environ.get("ESA_TEST_BROKER") == "1", "Essais broker explicites : ESA_TEST_BROKER=1")
class TestsBrokerT13(BancComptes):
    def setUp(self):
        super().setUp()
        self.broker = BancBroker()
        self.addCleanup(self.broker.fermer)
        self.broker.demarrer()
        self.config = ConfigurationMQTT("127.0.0.1", self.broker.port, "esa/Equipe_1", False)
        self.pi = TransportMQTT(self.config, "pi")
        self.supervision = SupervisionT13(AccesComptes(self.service), self.pi, periode=0.15)
        self.addCleanup(lambda: self.pi.fermer())
        self.pi.demarrer()
        self.chemin = self.racine / "pc.sqlite3"
        self.ouvrir_client()
        self.addCleanup(lambda: self.client.fermer())
        self.attendre(lambda: self.client.frais)

    def ouvrir_client(self):
        self.pc = TransportMQTT(self.config, "pc")
        self.journal = JournalDemandes(self.chemin, "test")
        self.client = ClientSupervision(self.pc, self.journal, repetition=0.25)
        self.pc.demarrer()

    def attendre(self, condition, delai=8, app=None):
        limite = time.monotonic() + delai
        while time.monotonic() < limite:
            self.supervision.actualiser()
            self.client.actualiser()
            if app:
                app.processEvents()
            if condition():
                return
            time.sleep(0.01)
        self.fail(f"Condition non atteinte : PC={self.pc.etat}, Pi={self.pi.etat}")

    def test_vrai_broker_credit_et_repetition(self):
        reference = self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        self.attendre(lambda: not self.journal.en_attente())
        self.assertEqual(self.solde(), 2500)
        self.client.reprendre(reference)
        self.attendre(lambda: not self.journal.en_attente())
        self.assertTrue(self.journal.historique()[0]["reponse"]["donnees"]["recu"]["deja_traitee"])
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_broker_isole_equipe_1_des_quatre_autres_equipes(self):
        autres = []
        for equipe in range(2, 6):
            config = ConfigurationMQTT("127.0.0.1", self.broker.port, f"esa/Equipe_{equipe}", False)
            for role in ("pi", "pc"):
                transport = TransportMQTT(config, role)
                autres.append(transport)
                self.addCleanup(transport.fermer)
                transport.demarrer()
        self.attendre(lambda: all(t.etat[0] for t in autres))
        self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        self.attendre(lambda: not self.journal.en_attente())
        self.assertEqual(self.solde(), 2500)
        receptions = [(t.role, t.config.prefixe, [m.topic for m in t.recevoir(maximum=256)]) for t in autres]
        self.assertTrue(all(not sujets for _, _, sujets in receptions), receptions)

    def test_vrai_broker_reponse_perdue_et_redemarrage_des_deux_clients(self):
        publier = self.pi.publier
        def perdre(nom, valeur, **options):
            return True if nom.endswith("/reponse") else publier(nom, valeur, **options)
        reference = self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        with patch.object(self.pi, "publier", perdre):
            self.attendre(lambda: self.solde() == 2500)
        self.assertEqual(self.journal.en_attente()[0]["id_commande"], reference)
        self.client.fermer()
        self.pi.fermer()
        self.pi = TransportMQTT(self.config, "pi")
        self.supervision = SupervisionT13(AccesComptes(self.nouveau_service()), self.pi, periode=0.15)
        self.pi.demarrer()
        self.ouvrir_client()
        self.attendre(lambda: self.client.frais and not self.journal.en_attente())
        recu = self.journal.historique()[0]["reponse"]["donnees"]["recu"]
        self.assertEqual(recu["id_transaction"], reference)
        self.assertTrue(recu["deja_traitee"])
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_arret_broker_reconnexion_et_resynchronisation_soldes_locaux(self):
        self.broker.fermer()
        self.attendre(lambda: not self.pc.etat[0] and not self.pi.etat[0])
        self.assertFalse(self.client.frais)
        self.service.crediter("credit-pendant-coupure", JASON, 125)
        avant = time.monotonic()
        for _ in range(100):
            self.supervision.actualiser()
        self.assertLess(time.monotonic() - avant, 0.5)
        self.broker.demarrer()
        self.attendre(lambda: self.client.frais and self.client.etat["soldes"][JASON] == 2125, delai=12)
        self.assertGreaterEqual(self.pc.etat[1], 2)
        self.assertGreaterEqual(self.pi.etat[1], 2)

    def test_fenetre_pc_qt_vrai_broker_credit_et_perte_connexion(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication
        from pc.interface import FenetreSupervision, PontPC
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        pont = PontPC(self.config, self.racine / "pc-qt.sqlite3")
        fenetre = FenetreSupervision(pont)
        def fermer():
            fenetre.close()
            limite = time.monotonic() + 4
            while pont.thread.isRunning() and time.monotonic() < limite:
                app.processEvents()
                time.sleep(0.01)
            self.assertFalse(pont.thread.isRunning())
        self.addCleanup(fermer)
        fenetre.show()
        pont.thread.start()
        fenetre.afficher_page(1)
        fenetre.carte.setText(JASON)
        self.attendre(lambda: fenetre.crediter.isEnabled(), app=app)
        fenetre.crediter.click()
        self.attendre(lambda: self.solde() == 2500 and fenetre.crediter.isEnabled(), app=app)
        self.assertTrue(all(not b.isEnabled() for b in fenetre.commandes_service.values()))
        self.assertEqual(len(fenetre.places), 14)
        self.assertEqual(len(self.lignes_journal()), 1)
        fenetre.afficher_page(2)
        app.processEvents()
        reference = fenetre.demandes.item(0, 0).text()
        rectangle = fenetre.demandes.visualItemRect(fenetre.demandes.item(0, 1))
        QTest.mouseClick(fenetre.demandes.viewport(), Qt.MouseButton.LeftButton,
                         pos=rectangle.center())
        self.attendre(lambda: fenetre.reprendre.isEnabled(), app=app)
        fenetre.reprendre.click()
        self.attendre(lambda: "déjà traitée" in fenetre.demandes.item(0, 2).text(), app=app)
        self.assertEqual(fenetre.demandes.item(0, 0).text(), reference)
        self.assertEqual(self.solde(), 2500)
        self.assertEqual(len(self.lignes_journal()), 1)
        self.broker.fermer()
        self.attendre(lambda: "Déconnecté" in fenetre.connexion.text(), app=app)
        self.assertFalse(fenetre.crediter.isEnabled())
        self.assertIn("périmées", fenetre.connexion.text())

    def test_fabrique_mqtt_dans_thread_t02_partage_les_comptes_et_ferme(self):
        from PyQt6.QtWidgets import QApplication
        from interface.qt.pont_t02 import PontT02Qt
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        ancienne_session = self.client.etat["session"]
        self.pi.fermer()  # Un seul serveur Pi pour ce prefixe.
        options = {"ESA_T13_ACTIVER": "1", "ESA_MQTT_HOTE": self.config.hote,
                   "ESA_MQTT_PORT": str(self.config.port), "ESA_MQTT_PREFIXE": self.config.prefixe,
                   "ESA_MQTT_TLS": "0"}
        pont = PontT02Qt(self.dossier, simulation=True)
        erreurs, reponses = [], {}
        pont.erreur.connect(erreurs.append)
        pont.reponse.connect(lambda ref, action, valeur: reponses.update({ref: valeur}))
        def fermer():
            pont.arreter()
            limite = time.monotonic() + 4
            while pont.en_cours and time.monotonic() < limite:
                app.processEvents()
                time.sleep(0.01)
            self.assertFalse(pont.en_cours)
        self.addCleanup(fermer)
        with patch.dict(os.environ, options):
            pont.demarrer()
            self.attendre(lambda: self.client.frais and self.client.etat["session"] != ancienne_session, app=app)
            self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
            self.attendre(lambda: not self.journal.en_attente(), app=app)
            reference_qt = pont.lister_soldes()
            self.attendre(lambda: reference_qt in reponses, app=app)
            self.assertEqual(reponses[reference_qt][JASON], 2500)
            fermer()
        self.assertEqual(erreurs, [])
        self.assertEqual(len(self.lignes_journal()), 1)


if __name__ == "__main__":
    unittest.main()
