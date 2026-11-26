"""Commandes de service via un vrai broker local ; T11/T12/CAN simules."""

import os
from pathlib import Path
import sys
import unittest

PROG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROG))
sys.path.insert(0, str(PROG / "rpi"))

import test_t13_broker as banc
from test_comptes_transactions import BancComptes
from exemples.systeme_t13_simule import SystemeT13Simule
from modules.service_t13 import GestionServiceT13
from modules.supervision import SupervisionT13


@unittest.skipUnless(os.environ.get("ESA_TEST_BROKER") == "1", "ESA_TEST_BROKER=1 requis")
class TestsServiceBroker(BancComptes):
    attendre = banc.TestsBrokerT13.attendre
    ouvrir_client = banc.TestsBrokerT13.ouvrir_client

    def setUp(self):
        super().setUp()
        self.broker = banc.BancBroker()
        self.broker.demarrer()
        self.addCleanup(self.broker.fermer)
        self.config = banc.ConfigurationMQTT("127.0.0.1", self.broker.port, "esa/Equipe_1", False)
        self.pi = banc.TransportMQTT(self.config, "pi")
        self.simule = SystemeT13Simule()
        self.gestion = GestionServiceT13(self.simule, self.racine / "service.sqlite3")
        self.supervision = SupervisionT13(banc.AccesComptes(self.service), self.pi,
                                         periode=0.1, service=self.gestion)
        self.addCleanup(self.supervision.fermer)
        self.pi.demarrer()
        self.chemin = self.racine / "pc.sqlite3"
        self.ouvrir_client()
        self.addCleanup(lambda: self.client.fermer())
        self.attendre(lambda: self.client.frais)

    def commander(self, action):
        identifiant = self.client.demander(action)
        self.attendre(lambda: not self.journal.en_attente())
        return identifiant, self.journal.historique()[0]["reponse"]

    def test_cycle_service_arret_refus_intervention_rearmement(self):
        self.commander("REMETTRE_EN_SERVICE")
        self.simule.injecter("depot")
        demande = self.client.demander("METTRE_HORS_SERVICE")
        self.attendre(lambda: self.client.etat["etat_service"] == "MISE_HORS_SERVICE")
        self.assertEqual(self.journal.historique()[0]["reponse"]["phase"], "ACCEPTEE")
        self.simule.injecter("fin-sequence")
        self.attendre(lambda: not self.journal.en_attente())
        self.assertEqual(self.journal.historique()[0]["reponse"]["id_commande"], demande)
        arret, _ = self.commander("ARRET_IMMEDIAT")
        self.client.reprendre(arret)
        self.attendre(lambda: not self.journal.en_attente())
        self.assertEqual(self.simule.arrets, 1)
        _, resultat = self.commander("REINITIALISER")
        self.assertEqual(resultat["code"], "REARMEMENT_NON_SUR")
        self.simule.injecter("intervention")
        _, resultat = self.commander("REINITIALISER")
        self.assertEqual(resultat["code"], "HORS_SERVICE")
        self.attendre(lambda: self.client.etat["etat_service"] == "HORS_SERVICE")
        self.assertFalse(self.simule.nouvelles)
        self.assertEqual(self.simule.demarrages, 1)

    def test_coupure_broker_ne_bloque_pas_fin_locale_et_resynchronise(self):
        self.commander("REMETTRE_EN_SERVICE")
        self.simule.injecter("retrait")
        self.client.demander("METTRE_HORS_SERVICE")
        self.attendre(lambda: self.client.etat["etat_service"] == "MISE_HORS_SERVICE")
        self.broker.fermer()
        self.attendre(lambda: not self.pi.etat[0] and not self.pc.etat[0])
        self.simule.injecter("fin-sequence")
        self.supervision.actualiser()
        self.assertEqual(self.gestion.etat, "MISE_HORS_SERVICE")
        self.simule.injecter("retirer-vehicule")
        self.supervision.actualiser()
        self.assertEqual(self.gestion.etat, "HORS_SERVICE")
        self.broker.demarrer()
        self.attendre(lambda: self.client.frais and not self.journal.en_attente())
        self.assertEqual(self.client.etat["etat_service"], "HORS_SERVICE")
        self.assertEqual(self.journal.historique()[0]["reponse"]["phase"], "TERMINEE")


if __name__ == "__main__":
    unittest.main()
