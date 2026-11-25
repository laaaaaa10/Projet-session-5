"""Contrat public T04/T02 et branchement reel, avec stockage temporaire."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import replace
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

RPI = Path(__file__).resolve().parents[1] / "rpi"
sys.path.insert(0, str(RPI))

from api.paiements import (
    ConflitTransaction, DemandePaiement, ErreurStockage, InterfacePaiement,
    PaiementEnCours, StatutOperation,
)
from application import integration_t04
from application.borne import Borne
from exemples.client_t04 import ClientT04Exemple
import main as programme
from modules.lecteur_nfc_rfid import EvenementRFID
from stockage import comptes_csv as stockage
from test_comptes_transactions import BancComptes, JASON, LUCIA
from test_rfid_integration import BancSimule, BADGE_B


class TestsInterfaceT04(BancComptes):
    def setUp(self):
        super().setUp()
        self.borne = Borne(self.service, Mock())

    def badge(self):
        self.borne.traiter_evenement(EvenementRFID("ACCEPTE", "essai", JASON))

    def test_api_publique_importable_sans_stockage_ni_bibliotheque_materielle(self):
        code = (
            "import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "sys.modules.update(serial=None, gpiozero=None, lgpio=None, fcntl=None)\n"
            "from api.paiements import *\n"
            "from exemples.client_t04 import ClientT04Exemple\n"
            "assert VERSION_INTERFACE == 1\n"
            "assert DemandePaiement('p', 550).montant_centimes == 550\n"
            "assert 'stockage.comptes_csv' not in sys.modules\n"
            "assert 'modules.lecteur_nfc_rfid' not in sys.modules\n"
        )
        resultat = subprocess.run(
            [sys.executable, "-B", "-c", code, str(RPI)],
            capture_output=True, text=True, cwd=self.racine,
        )
        self.assertEqual(resultat.returncode, 0, resultat.stderr)

    def test_borne_implemente_le_contrat_et_les_erreurs_publiques(self):
        self.assertIsInstance(self.borne, InterfacePaiement)
        self.borne.demander_paiement(DemandePaiement("p", 550))
        with self.assertRaises(PaiementEnCours):
            self.borne.demander_paiement(DemandePaiement("autre", 550))
        with self.assertRaises(ConflitTransaction):
            self.borne.demander_paiement(DemandePaiement("p", 600))
        self.assertEqual(self.solde(), 2000)

    def test_recherche_durable_ne_vide_pas_la_file_et_ne_redebite_pas(self):
        self.assertIsNone(self.borne.retrouver_resultat_paiement("inconnu"))
        self.borne.demander_paiement(DemandePaiement("p", 550))
        self.assertIsNone(self.borne.retrouver_resultat_paiement("p"))
        self.badge()
        for _ in range(2):
            retrouve = self.borne.retrouver_resultat_paiement("p")
            self.assertEqual(retrouve.statut, StatutOperation.PAIE)
            self.assertTrue(retrouve.deja_traitee)
        notifications = self.borne.lire_resultats_paiement()
        self.assertEqual(len(notifications), 1)
        self.assertFalse(notifications[0].deja_traitee)
        self.assertEqual(retrouve, replace(notifications[0], deja_traitee=True))
        nouvelle = Borne(self.nouveau_service(), Mock())
        self.assertEqual(nouvelle.retrouver_resultat_paiement("p"), retrouve)
        self.assertEqual(nouvelle.lire_resultats_paiement(), [])
        self.assertEqual(self.solde(), 1450)
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_recherche_et_annulation_valident_les_ids(self):
        for identifiant in ("", None, "avec espace"):
            for methode in (self.borne.retrouver_resultat_paiement, self.borne.annuler_paiement):
                with self.subTest(id=identifiant, methode=methode), self.assertRaises(ValueError):
                    methode(identifiant)
        self.assertEqual(self.lignes_journal(), [])

    def test_recherche_de_credit_refusee_par_l_api_de_paiement(self):
        self.service.crediter("credit", JASON, 100)
        with self.assertRaises(ConflitTransaction):
            self.borne.retrouver_resultat_paiement("credit")
        self.assertEqual(self.borne.lire_resultats_paiement(), [])

    def test_retransmission_historique_preserve_une_autre_attente(self):
        self.borne.demander_paiement(DemandePaiement("ancien", 500))
        self.badge()
        self.borne.lire_resultats_paiement()
        self.borne.demander_paiement(DemandePaiement("nouveau", 200))
        self.borne.demander_paiement(DemandePaiement("ancien", 500))
        self.assertTrue(self.borne.lire_resultats_paiement()[0].deja_traitee)
        self.badge()
        resultat = self.borne.lire_resultats_paiement()[0]
        self.assertEqual(resultat.id_transaction, "nouveau")
        self.assertEqual(self.solde(), 1300)

    def interrompre_apres_journal(self):
        self.borne.demander_paiement(DemandePaiement("p", 550))
        with patch.object(stockage, "_ecrire_comptes", side_effect=OSError("interruption")):
            with self.assertRaises(ErreurStockage):
                self.badge()
        self.assertEqual(self.borne.lire_resultats_paiement(), [])

    def test_reprise_apres_erreur_renvoie_resultat_sans_nouveau_badge(self):
        self.interrompre_apres_journal()
        self.borne.demander_paiement(DemandePaiement("p", 550))
        resultat = self.borne.lire_resultats_paiement()[0]
        self.assertEqual(resultat.statut, StatutOperation.PAIE)
        self.assertTrue(resultat.deja_traitee)
        self.assertFalse(self.borne.annuler_paiement("p"))
        self.borne.demander_paiement(DemandePaiement("suivant", 100))
        self.assertEqual(self.solde(), 1450)
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_annuler_apres_erreur_ne_cache_pas_un_paiement_deja_enregistre(self):
        self.interrompre_apres_journal()
        self.assertFalse(self.borne.annuler_paiement("p"))
        resultat = self.borne.lire_resultats_paiement()[0]
        self.assertEqual(resultat.statut, StatutOperation.PAIE)
        self.assertTrue(resultat.deja_traitee)
        self.borne.affichage.annulation.assert_not_called()
        self.assertEqual(self.solde(), 1450)
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_annulation_indisponible_ne_signale_pas_un_succes(self):
        self.borne.demander_paiement(DemandePaiement("p", 550))
        with patch.object(self.service, "retrouver_operation", side_effect=ErreurStockage("disque")):
            with self.assertRaises(ErreurStockage):
                self.borne.annuler_paiement("p")
        self.borne.affichage.annulation.assert_not_called()
        self.assertTrue(self.borne.annuler_paiement("p"))
        self.badge()
        self.assertEqual(self.solde(), 2000)

    def test_client_exemple_ne_repete_pas_ses_effets_sur_retransmission(self):
        client = ClientT04Exemple(self.borne)
        with redirect_stdout(io.StringIO()) as sortie:
            client.payer_facture("p", 550)
            client.actualiser()
            self.assertEqual(client.resultats, {})
            self.badge()
            client.actualiser()
            client.payer_facture("p", 550)
            client.actualiser()
        self.assertEqual(sortie.getvalue().count("Facture payee"), 1)
        self.assertEqual(set(client.resultats), {"p"})
        self.assertEqual(self.solde(), 1450)


class TestsBranchementT04(unittest.TestCase):
    def test_branchement_par_defaut_nactive_aucun_t04(self):
        paiements = Mock()
        self.assertIsNone(integration_t04.creer_module_t04(paiements))
        paiements.assert_not_called()
        self.assertEqual(paiements.mock_calls, [])

    def test_vrai_main_avec_client_t04_et_vrai_lecteur_simule(self):
        banc = BancSimule()
        clients = []
        passages = 0

        def creer(paiements):
            self.assertIsInstance(paiements, InterfacePaiement)
            client = ClientT04Exemple(paiements)
            client.payer_facture("integration-001", 550)
            clients.append(client)
            return client

        def avancer(_):
            nonlocal passages
            passages += 1
            if passages == 1:
                banc.maintenant = 1
                banc.rng.definir(True)
                banc.uart.tampon.extend(BADGE_B)
            else:
                raise KeyboardInterrupt

        with TemporaryDirectory() as dossier, ExitStack() as ressources:
            banc.installer(ressources)
            ressources.enter_context(patch.object(integration_t04, "creer_module_t04", creer))
            ressources.enter_context(patch("application.borne.time.sleep", avancer))
            sortie = ressources.enter_context(redirect_stdout(io.StringIO()))
            erreur = ressources.enter_context(redirect_stderr(io.StringIO()))
            self.assertEqual(programme.main([], dossier_donnees=dossier), 0, erreur.getvalue())
            self.assertEqual(stockage.charger_comptes(Path(dossier) / "comptes.csv")[JASON].solde_centimes, 1450)
        self.assertEqual(clients[0].resultats["integration-001"].statut, StatutOperation.PAIE)
        self.assertIn("T04 EXEMPLE | integration-001 | Facture payee", sortie.getvalue())
        self.assertEqual(banc.fermetures, ["uart", "rng", "fabrique"])

    def test_erreur_t04_libere_le_lecteur_et_nannonce_pas_de_paiement(self):
        banc = BancSimule()
        client = Mock()
        client.actualiser.side_effect = RuntimeError("erreur T04")
        with TemporaryDirectory() as dossier, ExitStack() as ressources:
            banc.installer(ressources)
            ressources.enter_context(patch.object(integration_t04, "creer_module_t04", return_value=client))
            sortie = ressources.enter_context(redirect_stdout(io.StringIO()))
            erreur = ressources.enter_context(redirect_stderr(io.StringIO()))
            self.assertEqual(programme.main([], dossier_donnees=dossier), 1)
            self.assertEqual(stockage.charger_comptes(Path(dossier) / "comptes.csv")[JASON].solde_centimes, 2000)
        self.assertIn("erreur T04", erreur.getvalue())
        self.assertNotIn("BORNE | PAIE", sortie.getvalue())
        self.assertEqual(banc.fermetures, ["uart", "rng", "fabrique"])

    def test_demo_sur_pc_sans_toucher_aux_donnees_actives(self):
        with TemporaryDirectory() as dossier:
            code = (
                "import runpy, sys\n"
                "sys.modules.update(serial=None, gpiozero=None, lgpio=None)\n"
                "runpy.run_path(sys.argv[1], run_name='__main__')\n"
            )
            resultat = subprocess.run(
                [sys.executable, "-B", "-c", code, str(RPI / "outils/demo_interface_t04.py")],
                cwd=dossier, capture_output=True, text=True,
            )
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertIn("Jason Duval | Solde final : 14,50 $", resultat.stdout)
        self.assertIn("Lucia Caminos | Solde final : 20,00 $", resultat.stdout)
        self.assertIn("Reprise : deja_traitee=True", resultat.stdout)
        self.assertIn("Refus : SOLDE_INSUFFISANT", resultat.stdout)
        self.assertIn("Refus : COMPTE_INCONNU", resultat.stdout)


if __name__ == "__main__":
    unittest.main()
