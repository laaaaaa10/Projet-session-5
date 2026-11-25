"""Regles de service T13 : doubles mecaniques explicites, journal SQLite reel."""

from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

PROG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROG))
sys.path.insert(0, str(PROG / "rpi"))

from commun.t13.protocole import nouvelle_commande
from exemples.systeme_t13_simule import SystemeT13Simule
from modules.service_t13 import GestionServiceT13


class TestsServiceT13(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temps = 0.0
        self.chemin = Path(self.temp.name) / "service.sqlite3"
        self.adaptateur = SystemeT13Simule(horloge=lambda: self.temps)
        self.service = GestionServiceT13(self.adaptateur, self.chemin, horloge=lambda: self.temps)
        self.addCleanup(lambda: self.service.fermer())

    def commander(self, action):
        return self.service.traiter(nouvelle_commande(action))

    def test_demarrage_hors_service_et_activation_expresse(self):
        self.assertEqual(self.service.etat, "HORS_SERVICE")
        self.adaptateur.injecter("depot")
        self.assertEqual(self.adaptateur.demarrages, 0)
        resultat = self.commander("REMETTRE_EN_SERVICE")
        self.assertEqual([r["phase"] for r in resultat], ["ACCEPTEE", "TERMINEE"])
        self.adaptateur.injecter("depot")
        self.assertEqual(self.adaptateur.demarrages, 1)

    def test_hors_service_annule_reservation_et_attend_retrait_vehicule(self):
        self.commander("REMETTRE_EN_SERVICE")
        self.adaptateur.injecter("reservation")
        resultat = self.commander("METTRE_HORS_SERVICE")[-1]
        self.assertEqual(self.adaptateur.annulations, 1)
        self.assertEqual(self.service.etat, "HORS_SERVICE")
        self.assertTrue(resultat["donnees"]["retrait_vehicule_requis"])
        self.assertEqual(self.commander("REMETTRE_EN_SERVICE")[-1]["code"], "SYSTEME_NON_PRET")
        self.adaptateur.injecter("retirer-vehicule")
        self.assertEqual(self.commander("REMETTRE_EN_SERVICE")[-1]["phase"], "TERMINEE")

    def test_hors_service_depot_confirme_finit_sans_nouvelle_transaction(self):
        self.commander("REMETTRE_EN_SERVICE")
        self.adaptateur.injecter("depot")
        demande = nouvelle_commande("METTRE_HORS_SERVICE")
        resultat = self.service.traiter(demande)
        self.assertEqual([r["phase"] for r in resultat], ["ACCEPTEE"])
        self.assertEqual(self.service.etat, "MISE_HORS_SERVICE")
        self.adaptateur.injecter("retrait")
        self.assertEqual(self.adaptateur.demarrages, 1)
        self.assertEqual(self.commander("REMETTRE_EN_SERVICE")[-1]["code"], "COMMANDE_EN_COURS")
        self.adaptateur.injecter("fin-sequence")
        resultat = self.service.actualiser()[-1]
        self.assertEqual(resultat["id_commande"], demande["id_commande"])
        self.assertEqual(resultat["phase"], "TERMINEE")
        self.assertEqual(self.service.etat, "HORS_SERVICE")
        self.assertEqual(self.adaptateur.arrets, 0)

    def test_hors_service_retrait_confirme_attend_sortie_manuelle(self):
        self.commander("REMETTRE_EN_SERVICE")
        self.adaptateur.injecter("retrait")
        self.commander("METTRE_HORS_SERVICE")
        self.adaptateur.injecter("fin-sequence")
        self.assertEqual(self.service.actualiser(), [])
        self.assertEqual(self.service.etat, "MISE_HORS_SERVICE")
        self.assertEqual(self.adaptateur.sequence, "ATTENTE_RETRAIT_MANUEL")
        self.adaptateur.injecter("retirer-vehicule")
        self.assertEqual(self.service.actualiser()[-1]["phase"], "TERMINEE")
        self.assertEqual(self.service.etat, "HORS_SERVICE")

    def test_arret_interrompt_commande_en_cours_et_reste_verrouille(self):
        self.commander("REMETTRE_EN_SERVICE")
        self.adaptateur.injecter("depot")
        demande = nouvelle_commande("METTRE_HORS_SERVICE")
        self.service.traiter(demande)
        resultat = self.commander("ARRET_IMMEDIAT")
        self.assertEqual(resultat[0]["id_commande"], demande["id_commande"])
        self.assertEqual(resultat[0]["code"], "INTERROMPUE_PAR_ARRET")
        self.assertEqual(self.adaptateur.sequence, "INTERROMPUE")
        self.assertEqual(self.service.etat, "ARRET_VERROUILLE")
        for action in ("REMETTRE_EN_SERVICE", "METTRE_HORS_SERVICE"):
            self.assertEqual(self.commander(action)[-1]["code"], "ARRET_VERROUILLE")
        self.adaptateur.injecter("fin-sequence")
        self.service.actualiser()
        self.assertEqual(self.service.etat, "ARRET_VERROUILLE")

    def test_repetition_id_ne_reexecute_ni_arret_ni_ancienne_remise_en_service(self):
        activer = nouvelle_commande("REMETTRE_EN_SERVICE")
        self.service.traiter(activer)
        arret = nouvelle_commande("ARRET_IMMEDIAT")
        self.service.traiter(arret)
        self.assertTrue(self.service.traiter(arret)[-1]["donnees"]["deja_traitee"])
        self.assertEqual(self.adaptateur.arrets, 1)
        self.service.traiter(activer)
        self.assertEqual(self.service.etat, "ARRET_VERROUILLE")
        conflit = dict(arret, commande="REMETTRE_EN_SERVICE")
        self.assertEqual(self.service.traiter(conflit)[-1]["code"], "CONFLIT_COMMANDE")

    def test_conditions_rearmement_toutes_requises(self):
        self.commander("ARRET_IMMEDIAT")
        self.assertEqual(self.commander("REINITIALISER")[-1]["code"], "REARMEMENT_NON_SUR")
        self.adaptateur.injecter("intervention")
        initiales = self.adaptateur.conditions()
        for champ in ("defauts_leves", "intervention_confirmee", "bras_retracte_sur",
                      "reference_verticale", "reference_angulaire"):
            with self.subTest(champ=champ), patch.object(
                    self.adaptateur, "conditions", return_value=replace(initiales, **{champ: False})):
                self.assertEqual(self.commander("REINITIALISER")[-1]["code"], "REARMEMENT_NON_SUR")
        self.assertEqual(self.adaptateur.rearmements, 0)

    def test_rearmement_attend_confirmation_et_ne_reprend_pas_mouvement(self):
        self.commander("REMETTRE_EN_SERVICE")
        self.adaptateur.injecter("depot")
        self.commander("ARRET_IMMEDIAT")
        self.adaptateur.injecter("intervention")
        demande = nouvelle_commande("REINITIALISER")
        self.assertEqual(self.service.traiter(demande)[-1]["phase"], "ACCEPTEE")
        self.assertEqual(self.service.actualiser(), [])
        self.assertEqual(self.service.etat, "ARRET_VERROUILLE")
        self.service.traiter(demande)
        self.assertEqual(self.adaptateur.rearmements, 1)
        self.temps += 1
        self.assertEqual(self.service.actualiser()[-1]["phase"], "TERMINEE")
        self.assertEqual(self.service.etat, "HORS_SERVICE")
        self.assertEqual(self.adaptateur.demarrages, 1)
        self.assertFalse(self.adaptateur.nouvelles)
        self.service.traiter(demande)
        self.assertEqual(self.adaptateur.rearmements, 1)

    def test_rearmement_refuse_ou_sans_reponse_garde_verrou(self):
        for mode, code in (("refuse", "REARMEMENT_REFUSE"), ("muet", "REARMEMENT_SANS_REPONSE")):
            with self.subTest(mode=mode):
                self.commander("ARRET_IMMEDIAT")
                self.adaptateur.injecter("intervention")
                self.adaptateur.injecter("rearmement-" + mode)
                self.commander("REINITIALISER")
                self.temps += 6
                resultat = self.service.actualiser()[-1]
                self.assertEqual(resultat["code"], code)
                self.assertEqual(resultat["phase"], "REFUSEE")
                self.assertEqual(self.service.etat, "ARRET_VERROUILLE")
                self.assertFalse(self.adaptateur.nouvelles)

    def test_conditions_perdues_pendant_rearmement_refusent_fin(self):
        self.commander("ARRET_IMMEDIAT")
        self.adaptateur.injecter("intervention")
        self.commander("REINITIALISER")
        self.adaptateur.injecter("reference-invalide")
        self.temps += 1
        self.assertEqual(self.service.actualiser()[-1]["code"], "REARMEMENT_NON_SUR")
        self.assertEqual(self.service.etat, "ARRET_VERROUILLE")

    def test_nouvel_arret_annule_rearmement_en_cours(self):
        self.commander("ARRET_IMMEDIAT")
        self.adaptateur.injecter("intervention")
        demande = nouvelle_commande("REINITIALISER")
        self.service.traiter(demande)
        self.commander("ARRET_IMMEDIAT")
        self.temps += 10
        self.service.actualiser()
        self.assertEqual(self.service.traiter(demande)[-1]["code"], "INTERROMPUE_PAR_ARRET")
        self.assertEqual(self.service.etat, "ARRET_VERROUILLE")

    def test_defaut_critique_verrouille_et_interrompt_attente(self):
        self.commander("REMETTRE_EN_SERVICE")
        self.adaptateur.injecter("depot")
        self.commander("METTRE_HORS_SERVICE")
        self.adaptateur.injecter("defaut")
        self.assertEqual(self.service.actualiser()[-1]["code"], "INTERROMPUE_PAR_DEFAUT")
        self.assertEqual(self.service.etat, "ARRET_VERROUILLE")
        self.assertFalse(self.adaptateur.nouvelles)

    def test_redemarrage_conserve_arret_et_resultat_identifie(self):
        demande = nouvelle_commande("ARRET_IMMEDIAT")
        self.service.traiter(demande)
        self.service.fermer()
        self.adaptateur = SystemeT13Simule()
        self.service = GestionServiceT13(self.adaptateur, self.chemin)
        self.assertEqual(self.service.etat, "ARRET_VERROUILLE")
        self.assertTrue(self.service.traiter(demande)[-1]["donnees"]["deja_traitee"])
        self.assertEqual(self.adaptateur.demarrages, 0)

    def test_redemarrage_pendant_rearmement_ne_deverrouille_pas(self):
        self.commander("ARRET_IMMEDIAT")
        self.adaptateur.injecter("intervention")
        demande = nouvelle_commande("REINITIALISER")
        self.service.traiter(demande)
        self.service.fermer()
        self.adaptateur = SystemeT13Simule()
        self.service = GestionServiceT13(self.adaptateur, self.chemin)
        self.assertEqual(self.service.traiter(demande)[-1]["code"], "REDEMARRAGE_INTERROMPU")
        self.assertEqual(self.service.etat, "ARRET_VERROUILLE")
        self.assertEqual(self.adaptateur.rearmements, 0)

    def test_redemarrage_en_service_reste_hors_service(self):
        ancienne = nouvelle_commande("REMETTRE_EN_SERVICE")
        self.service.traiter(ancienne)
        self.service.fermer()
        self.service = GestionServiceT13(self.adaptateur, self.chemin)
        self.service.traiter(ancienne)
        self.assertEqual(self.service.etat, "HORS_SERVICE")
        self.assertFalse(self.adaptateur.nouvelles)

    def test_pas_de_rejeu_ancien_scenario_au_demarrage(self):
        chemin = Path(self.temp.name) / "scenario.json"
        chemin.write_text(json.dumps({"id": "ancien", "action": "depot"}))
        simule = SystemeT13Simule(chemin)
        simule.autoriser_nouvelles(True)
        simule.actualiser()
        self.assertEqual(simule.demarrages, 0)
        chemin.write_text(json.dumps({"id": "nouveau", "action": "retrait"}))
        simule.actualiser()
        self.assertEqual(simule.sequence, "RETRAIT_T12")

    def test_journal_service_ne_change_pas_de_cible(self):
        with self.assertRaisesRegex(ValueError, "autre broker"):
            GestionServiceT13(SystemeT13Simule(), self.chemin, cible="autre")


if __name__ == "__main__":
    unittest.main()
