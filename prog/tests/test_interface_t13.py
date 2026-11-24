"""Acces local T13/T02 sur le vrai service CSV ; aucun transport MQTT implemente."""

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

from api.comptes import ConflitTransaction, ErreurStockage, InterfaceComptes, StatutOperation
from api.paiements import DemandePaiement
from application import integration_t03, integration_t04, integration_t13
from application.acces_comptes import AccesComptes
from application.borne import Borne
import main as programme
from stockage import comptes_csv as stockage
from test_comptes_transactions import BancComptes, INCONNU, JASON, LUCIA
from test_rfid_integration import BancSimule, BADGE_A, BADGE_B


class TestsAccesT13(BancComptes):
    def setUp(self):
        super().setUp()
        self.acces = AccesComptes(self.service)

    def test_contrat_sans_debit_ni_creation_et_import_sans_materiel(self):
        self.assertIsInstance(self.acces, InterfaceComptes)
        for nom in ("payer", "demander_paiement", "creer_compte"):
            self.assertFalse(hasattr(self.acces, nom))
        code = (
            "import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "sys.modules.update(serial=None, gpiozero=None, lgpio=None, fcntl=None)\n"
            "from api.comptes import *\n"
            "assert VERSION_INTERFACE == 1\n"
            "assert 'modules.lecteur_nfc_rfid' not in sys.modules\n"
            "assert 'stockage.comptes_csv' not in sys.modules\n"
        )
        resultat = subprocess.run([sys.executable, "-B", "-c", code, str(RPI)],
                                  cwd=self.racine, capture_output=True, text=True)
        self.assertEqual(resultat.returncode, 0, resultat.stderr)

    def test_consultation_zero_inconnu_et_synchronisation_sans_ecriture(self):
        self.service.payer("vider", JASON, 2000)
        avant = (self.dossier / "operations.csv").read_bytes()
        self.assertEqual(self.acces.consulter_solde(JASON.lower()), 0)
        self.assertIsNone(self.acces.consulter_solde(INCONNU))
        self.assertIsNone(self.acces.consulter_solde("12008827F9"))
        soldes = self.acces.lister_soldes()
        self.assertEqual(soldes, {JASON: 0, LUCIA: 2000})
        soldes[JASON] = 9999
        self.assertEqual(self.acces.consulter_solde(JASON), 0)
        self.assertEqual((self.dossier / "operations.csv").read_bytes(), avant)

    def test_credit_repete_apres_redemarrage_conserve_un_seul_mouvement(self):
        premier = self.acces.ajouter_credit("t13:001", JASON.lower(), 500)
        self.assertEqual(premier.statut, StatutOperation.CREDITE)
        self.assertFalse(premier.deja_traitee)
        acces = AccesComptes(self.nouveau_service())
        self.assertEqual(acces.ajouter_credit("t13:001", JASON, 500),
                         replace(premier, deja_traitee=True))
        self.assertEqual(acces.retrouver_resultat_credit("t13:001"),
                         replace(premier, deja_traitee=True))
        self.assertEqual(acces.consulter_solde(JASON), 2500)
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_resultat_historique_distinct_du_solde_courant(self):
        credit = self.acces.ajouter_credit("c", JASON, 500)
        self.service.payer("p", JASON, 1000)
        self.assertEqual(self.acces.retrouver_resultat_credit("c"),
                         replace(credit, deja_traitee=True))
        self.assertEqual(credit.solde_apres_centimes, 2500)
        self.assertEqual(self.acces.consulter_solde(JASON), 1500)
        self.assertIsNone(self.acces.retrouver_resultat_credit("absent"))
        self.assertEqual(len(self.lignes_journal()), 2)

    def test_id_partage_avec_paiements_et_conflits_sans_mouvement(self):
        self.acces.ajouter_credit("c", JASON, 500)
        self.service.payer("p", JASON, 200)
        for reference, carte, montant in (("c", JASON, 600), ("c", LUCIA, 500),
                                          ("p", JASON, 200)):
            with self.subTest(reference=reference, carte=carte, montant=montant):
                with self.assertRaises(ConflitTransaction):
                    self.acces.ajouter_credit(reference, carte, montant)
        with self.assertRaises(ConflitTransaction):
            self.acces.retrouver_resultat_credit("p")
        self.assertEqual(self.acces.lister_soldes(), {JASON: 2300, LUCIA: 2000})
        self.assertEqual(len(self.lignes_journal()), 2)

    def test_credit_inconnu_refuse_et_resultat_retrouvable(self):
        resultat = self.acces.ajouter_credit("c", INCONNU, 500)
        self.assertEqual(resultat.statut, StatutOperation.COMPTE_INCONNU)
        self.assertFalse(resultat.succes)
        self.assertIsNone(resultat.solde_apres_centimes)
        acces = AccesComptes(self.nouveau_service())
        self.assertEqual(acces.retrouver_resultat_credit("c"), replace(resultat, deja_traitee=True))
        self.assertTrue(acces.ajouter_credit("c", INCONNU, 500).deja_traitee)
        self.assertEqual(acces.lister_soldes(), {JASON: 2000, LUCIA: 2000})
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_parametres_invalides_rejetes_avant_ecriture(self):
        avant = (self.dossier / "operations.csv").read_bytes()
        for montant in (0, -1, True, 5.5, "500", None):
            with self.subTest(montant=montant), self.assertRaises(ValueError):
                self.acces.ajouter_credit("c", JASON, montant)
        for carte in ("", "008827F9", "11008827FZ", None):
            with self.subTest(carte=carte):
                with self.assertRaises(ValueError):
                    self.acces.consulter_solde(carte)
                with self.assertRaises(ValueError):
                    self.acces.ajouter_credit("c", carte, 500)
        for reference in ("", "avec espace", "../c", "x" * 129, None):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                self.acces.ajouter_credit(reference, JASON, 500)
        self.assertEqual((self.dossier / "operations.csv").read_bytes(), avant)

    def test_erreur_csv_remonte_sans_faux_compte_inconnu_ni_faux_credit(self):
        (self.dossier / "operations.csv").unlink()
        for action in (lambda: self.acces.consulter_solde(JASON),
                       self.acces.lister_soldes,
                       lambda: self.acces.ajouter_credit("c", JASON, 500),
                       lambda: self.acces.retrouver_resultat_credit("c")):
            with self.subTest(action=action), self.assertRaises(ErreurStockage):
                action()
        self.assertFalse((self.dossier / "operations.csv").exists())

    def test_reprise_credit_apres_erreur_soldes_ne_recredite_pas(self):
        with patch.object(stockage, "_ecrire_comptes", side_effect=OSError("interruption")):
            with self.assertRaises(ErreurStockage):
                self.acces.ajouter_credit("c", JASON, 500)
        acces = AccesComptes(self.nouveau_service())
        with self.assertLogs(stockage.JOURNAL_TECHNIQUE, level="WARNING"):
            resultat = acces.ajouter_credit("c", JASON, 500)
        self.assertTrue(resultat.deja_traitee)
        self.assertEqual(acces.consulter_solde(JASON), 2500)
        self.assertEqual(len(self.lignes_journal()), 1)


class TestsBranchementT13(unittest.TestCase):
    def test_branchement_par_defaut_desactive(self):
        acces = Mock()
        self.assertIsNone(integration_t13.creer_module_t13(acces))
        self.assertEqual(acces.mock_calls, [])

    def test_vrai_main_t03_t04_t13_partagent_les_soldes_et_un_lecteur(self):
        banc = BancSimule()
        lectures, paiements, credits, soldes = [], [], [], []
        etapes = iter(((1, True, BADGE_B), (2, False, b""), (3, True, BADGE_A)))

        def creer_t03(acces):
            return Mock(actualiser=lambda: lectures.extend(acces.lire_identifications()))

        def creer_t04(acces):
            acces.demander_paiement(DemandePaiement("t04:001", 2500))
            return Mock(actualiser=lambda: paiements.extend(acces.lire_resultats_paiement()))

        def creer_t13(acces):
            self.assertIsInstance(acces, InterfaceComptes)

            def actualiser():
                if not credits:
                    credits.append(acces.ajouter_credit("t13:001", JASON, 500))
                    credits.append(acces.ajouter_credit("t13:001", JASON, 500))
                soldes.append(acces.lister_soldes())

            return Mock(actualiser=actualiser)

        def avancer(_):
            try:
                instant, presente, donnees = next(etapes)
            except StopIteration:
                raise KeyboardInterrupt
            banc.maintenant = instant
            banc.rng.definir(presente)
            banc.uart.tampon.extend(donnees)

        with TemporaryDirectory() as dossier, ExitStack() as ressources:
            banc.installer(ressources)
            ressources.enter_context(patch.object(integration_t03, "creer_module_t03", creer_t03))
            ressources.enter_context(patch.object(integration_t04, "creer_module_t04", creer_t04))
            ressources.enter_context(patch.object(integration_t13, "creer_module_t13", creer_t13))
            ressources.enter_context(patch("application.borne.time.sleep", avancer))
            ressources.enter_context(redirect_stdout(io.StringIO()))
            erreur = ressources.enter_context(redirect_stderr(io.StringIO()))
            self.assertEqual(programme.main([], dossier_donnees=dossier), 0, erreur.getvalue())
            self.assertEqual(stockage.charger_comptes(Path(dossier) / "comptes.csv")[JASON].solde_centimes, 0)
        self.assertEqual([r.deja_traitee for r in credits], [False, True])
        self.assertEqual([(r.statut, r.solde_avant_centimes, r.solde_apres_centimes)
                          for r in paiements], [(StatutOperation.PAIE, 2500, 0)])
        self.assertEqual([(r.id_uart, r.solde_centimes) for r in lectures], [(LUCIA, 2000)])
        self.assertEqual(soldes[0], {JASON: 2500, LUCIA: 2000})
        self.assertEqual(soldes[-1], {JASON: 0, LUCIA: 2000})
        self.assertEqual(banc.chips, [0])
        self.assertEqual(banc.fermetures, ["uart", "rng", "fabrique"])

    def test_erreur_client_t13_libere_le_materiel(self):
        banc = BancSimule()
        client = Mock()
        client.actualiser.side_effect = RuntimeError("erreur client T13")
        with TemporaryDirectory() as dossier, ExitStack() as ressources:
            banc.installer(ressources)
            ressources.enter_context(patch.object(integration_t13, "creer_module_t13", return_value=client))
            ressources.enter_context(redirect_stdout(io.StringIO()))
            erreur = ressources.enter_context(redirect_stderr(io.StringIO()))
            self.assertEqual(programme.main([], dossier_donnees=dossier), 1)
        self.assertIn("erreur client T13", erreur.getvalue())
        self.assertEqual(banc.fermetures, ["uart", "rng", "fabrique"])

    def test_simulateur_un_paiement_refuse_un_module_t13_actif(self):
        borne = Borne(Mock(), Mock())
        lecteur = Mock()
        with self.assertRaises(ValueError):
            borne.executer(lecteur, un_paiement=True, t13=Mock())
        self.assertEqual(lecteur.mock_calls, [])

    def test_demo_sans_materiel_sur_donnees_temporaires(self):
        code = (
            "import runpy, sys\n"
            "sys.modules.update(serial=None, gpiozero=None, lgpio=None)\n"
            "runpy.run_path(sys.argv[1], run_name='__main__')\n"
        )
        with TemporaryDirectory() as dossier:
            resultat = subprocess.run(
                [sys.executable, "-B", "-c", code, str(RPI / "outils/demo_interface_t13.py")],
                cwd=dossier, capture_output=True, text=True,
            )
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertIn("Solde initial de Jason : 2000 centimes", resultat.stdout)
        self.assertIn("Solde apres credit : 2500 centimes | deja_traitee=False", resultat.stdout)
        self.assertIn("Solde apres credit : 2500 centimes | deja_traitee=True", resultat.stdout)
        self.assertIn("CONFLIT_TRANSACTION", resultat.stdout)
        self.assertIn("Carte inconnue : COMPTE_INCONNU", resultat.stdout)
        self.assertIn("Reprise : deja_traitee=True", resultat.stdout)
        self.assertIn(f"Solde courant : {JASON} | 2500 centimes", resultat.stdout)
        self.assertIn(f"Solde courant : {LUCIA} | 2000 centimes", resultat.stdout)


if __name__ == "__main__":
    unittest.main()
