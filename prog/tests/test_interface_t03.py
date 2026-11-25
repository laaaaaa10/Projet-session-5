"""Acces de T03 aux donnees T02 ; aucune logique de reservation testee ici."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

RPI = Path(__file__).resolve().parents[1] / "rpi"
sys.path.insert(0, str(RPI))

from api.identification import ErreurStockage, InterfaceIdentification
from api.paiements import DemandePaiement, StatutOperation
from application import integration_t03, integration_t04
from application.acces_identification import AccesIdentification
from application.borne import Borne
from exemples.client_t03 import ClientT03Exemple
from exemples.client_t04 import ClientT04Exemple
import main as programme
from modules import lecteur_nfc_rfid as rfid
from stockage.comptes_csv import charger_comptes
from test_comptes_transactions import BancComptes, INCONNU, JASON, LUCIA
from test_rfid_integration import BancSimule, BADGE_A, BADGE_B, BADGE_C


class TestsAccesT03(BancComptes):
    def setUp(self):
        super().setUp()
        self.acces = AccesIdentification(self.service)
        self.borne = Borne(self.service, Mock(), identification=self.acces)

    def badge(self, id_uart=JASON, type_evenement="ACCEPTE"):
        self.borne.traiter_evenement(rfid.EvenementRFID(type_evenement, "essai", id_uart))

    def test_contrat_en_lecture_seule_sans_materiel_ni_stockage_a_l_import(self):
        self.assertIsInstance(self.acces, InterfaceIdentification)
        self.assertFalse(hasattr(self.acces, "payer"))
        self.assertFalse(hasattr(self.acces, "crediter"))
        code = (
            "import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "sys.modules.update(serial=None, gpiozero=None, lgpio=None, fcntl=None)\n"
            "from api.identification import *\n"
            "from exemples.client_t03 import ClientT03Exemple\n"
            "assert VERSION_INTERFACE == 1\n"
            "assert 'modules.lecteur_nfc_rfid' not in sys.modules\n"
            "assert 'stockage.comptes_csv' not in sys.modules\n"
        )
        resultat = subprocess.run([sys.executable, "-B", "-c", code, str(RPI)],
                                  cwd=self.racine, capture_output=True, text=True)
        self.assertEqual(resultat.returncode, 0, resultat.stderr)

    def test_cartes_connues_et_inconnue_dans_ordre_sans_debit(self):
        for id_uart in (JASON, INCONNU, LUCIA):
            self.badge(id_uart)
        lectures = self.acces.lire_identifications()
        self.assertEqual([(r.id_uart, r.compte_connu, r.solde_centimes) for r in lectures],
                         [(JASON, True, 2000), (INCONNU, False, None), (LUCIA, True, 2000)])
        self.assertEqual(self.acces.lire_identifications(), [])
        self.assertEqual(self.lignes_journal(), [])
        self.assertEqual(self.solde(), 2000)
        self.assertEqual(self.solde(LUCIA), 2000)

    def test_solde_zero_reste_un_compte_connu(self):
        self.service.payer("vider", JASON, 2000)
        self.badge()
        lecture = self.acces.lire_identifications()[0]
        self.assertTrue(lecture.compte_connu)
        self.assertEqual(lecture.solde_centimes, 0)
        self.assertEqual(self.acces.consulter_solde(JASON), 0)

    def test_lecture_est_un_instantane_immuable_consultation_reste_a_jour(self):
        self.badge()
        lecture = self.acces.lire_identifications()[0]
        with self.assertRaises(FrozenInstanceError):
            lecture.solde_centimes = 9999
        self.service.payer("p", JASON, 500)
        self.assertEqual(lecture.solde_centimes, 2000)
        self.assertEqual(self.acces.consulter_solde(JASON.lower()), 1500)
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_consultation_ne_cree_pas_de_compte_et_utilise_id_complet(self):
        for id_uart in (INCONNU, "12008827F9"):
            self.assertIsNone(self.acces.consulter_solde(id_uart))
        for id_uart in ("008827F9", "", None, "11008827FZ"):
            with self.subTest(id_uart=id_uart), self.assertRaises(ValueError):
                self.acces.consulter_solde(id_uart)
        self.assertEqual(len(self.service.lister_comptes()), 2)
        self.assertEqual(self.lignes_journal(), [])
        self.assertEqual(self.acces.lire_identifications(), [])

    def test_autre_prefixe_ne_donne_pas_le_compte(self):
        self.badge("12008827F9")
        lecture = self.acces.lire_identifications()[0]
        self.assertEqual(lecture.id_uart, "12008827F9")
        self.assertFalse(lecture.compte_connu)

    def test_seules_les_lectures_acceptees_atteignent_t03(self):
        for type_evenement in ("INFO", "INVALIDE", "IGNORE", "PRESENCE", "RETRAIT"):
            self.badge(type_evenement=type_evenement)
        self.assertEqual(self.acces.lire_identifications(), [])
        self.badge()
        self.assertEqual(len(self.acces.lire_identifications()), 1)

    def test_rearmement_du_vrai_lecteur_ne_duplique_pas_les_lectures_t03(self):
        banc = BancSimule()
        with ExitStack() as ressources:
            banc.installer(ressources)
            lecteur = ressources.enter_context(rfid.LecteurRFID())
            for instant, presence, donnees in (
                (1, True, BADGE_B + BADGE_B),
                (1.1, True, BADGE_B),
                (2, False, b""),
                (2.1, True, BADGE_B),
            ):
                for evenement in banc.lire(lecteur, instant, presence, donnees):
                    self.borne.traiter_evenement(evenement)
            self.assertEqual(len(self.acces.lire_identifications()), 1)
            for evenement in banc.lire(lecteur, 3, False):
                self.borne.traiter_evenement(evenement)
            for evenement in banc.lire(lecteur, 3.5, True, BADGE_B):
                self.borne.traiter_evenement(evenement)
            self.assertEqual(len(self.acces.lire_identifications()), 1)

    def test_carte_utilisee_pour_payer_ne_notifie_pas_t03_meme_si_refus(self):
        for reference, id_uart, montant, statut in (
            ("paye", JASON, 500, StatutOperation.PAIE),
            ("solde", LUCIA, 2500, StatutOperation.SOLDE_INSUFFISANT),
            ("inconnu", INCONNU, 500, StatutOperation.COMPTE_INCONNU),
        ):
            with self.subTest(statut=statut):
                self.borne.demander_paiement(DemandePaiement(reference, montant))
                self.badge(id_uart)
                self.assertEqual(self.acces.lire_identifications(), [])
                resultat = self.borne.lire_resultats_paiement()[0]
                self.assertEqual(resultat.statut, statut)
        self.badge(JASON)  # Nouvelle lecture acceptee, plus de paiement en attente.
        self.assertEqual(self.acces.lire_identifications()[0].solde_centimes, 1500)

    def test_t03_ne_vide_pas_les_resultats_t04(self):
        self.badge(LUCIA)
        self.borne.demander_paiement(DemandePaiement("p", 500))
        self.badge(JASON)
        self.assertEqual(self.acces.consulter_solde(JASON), 1500)
        self.assertEqual([r.id_uart for r in self.acces.lire_identifications()], [LUCIA])
        self.assertEqual(len(self.borne.lire_resultats_paiement()), 1)
        self.assertEqual(self.acces.lire_identifications(), [])

    def test_erreur_fichier_ne_devient_pas_une_fausse_carte_inconnue(self):
        with patch.object(self.service, "consulter_compte", side_effect=ErreurStockage("CSV")):
            with self.assertRaises(ErreurStockage):
                self.badge()
            with self.assertRaises(ErreurStockage):
                self.acces.consulter_solde(JASON)
        self.assertEqual(self.acces.lire_identifications(), [])

    def test_client_exemple_consomme_les_lectures_une_fois(self):
        client = ClientT03Exemple(self.acces)
        self.badge(JASON)
        self.badge(INCONNU)
        with redirect_stdout(io.StringIO()) as sortie:
            client.actualiser()
            client.actualiser()
        self.assertEqual(sortie.getvalue().count("T03 EXEMPLE |"), 2)
        self.assertIn("Solde : 2000 centimes", sortie.getvalue())
        self.assertIn("Carte inconnue", sortie.getvalue())


class TestsBranchementT03(unittest.TestCase):
    def test_branchement_par_defaut_desactive(self):
        acces = Mock()
        self.assertIsNone(integration_t03.creer_module_t03(acces))
        self.assertEqual(acces.mock_calls, [])

    def test_vrai_main_avec_t03_et_t04_sans_second_lecteur(self):
        banc = BancSimule()
        identifications, clients_t04 = [], []
        etapes = iter(((1, True, BADGE_B), (2, False, b""), (3, True, BADGE_A),
                       (4, False, b""), (5, True, BADGE_C)))

        def creer_t03(acces):
            self.assertIsInstance(acces, InterfaceIdentification)
            return Mock(actualiser=lambda: identifications.extend(acces.lire_identifications()))

        def creer_t04(paiements):
            client = ClientT04Exemple(paiements)
            client.payer_facture("integration-001", 500)
            clients_t04.append(client)
            return client

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
            ressources.enter_context(patch("application.borne.time.sleep", avancer))
            ressources.enter_context(redirect_stdout(io.StringIO()))
            erreur = ressources.enter_context(redirect_stderr(io.StringIO()))
            self.assertEqual(programme.main([], dossier_donnees=dossier), 0, erreur.getvalue())
            self.assertEqual(charger_comptes(Path(dossier) / "comptes.csv")[JASON].solde_centimes, 1500)
        self.assertEqual([(r.id_uart, r.solde_centimes) for r in identifications],
                         [(LUCIA, 2000), (INCONNU, None)])
        self.assertEqual(clients_t04[0].resultats["integration-001"].statut, StatutOperation.PAIE)
        self.assertEqual(banc.chips, [0])
        self.assertEqual(banc.fermetures, ["uart", "rng", "fabrique"])

    def test_erreur_client_t03_libere_les_ressources(self):
        banc = BancSimule()
        client = Mock()
        client.actualiser.side_effect = RuntimeError("erreur client T03")
        with TemporaryDirectory() as dossier, ExitStack() as ressources:
            banc.installer(ressources)
            ressources.enter_context(patch.object(integration_t03, "creer_module_t03", return_value=client))
            ressources.enter_context(redirect_stdout(io.StringIO()))
            erreur = ressources.enter_context(redirect_stderr(io.StringIO()))
            self.assertEqual(programme.main([], dossier_donnees=dossier), 1)
        self.assertIn("erreur client T03", erreur.getvalue())
        self.assertEqual(banc.fermetures, ["uart", "rng", "fabrique"])

    def test_demo_sans_materiel_sur_donnees_temporaires(self):
        code = (
            "import runpy, sys\n"
            "sys.modules.update(serial=None, gpiozero=None, lgpio=None)\n"
            "runpy.run_path(sys.argv[1], run_name='__main__')\n"
        )
        with TemporaryDirectory() as dossier:
            resultat = subprocess.run(
                [sys.executable, "-B", "-c", code, str(RPI / "outils/demo_interface_t03.py")],
                cwd=dossier, capture_output=True, text=True,
            )
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertIn(f"T03 EXEMPLE | Carte : {JASON} | Solde : 2000 centimes", resultat.stdout)
        self.assertIn(f"T03 EXEMPLE | Carte inconnue : {INCONNU}", resultat.stdout)
        self.assertIn("Lectures T03 pendant le paiement : 0", resultat.stdout)
        self.assertIn("Resultats T04 disponibles : 1", resultat.stdout)
        self.assertIn("Solde courant de Jason : 1500 centimes", resultat.stdout)


if __name__ == "__main__":
    unittest.main()
