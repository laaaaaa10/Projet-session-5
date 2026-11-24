"""T02 : operations reelles sur des CSV temporaires, sans toucher aux soldes du Pi."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import csv
from dataclasses import replace
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import Mock, patch

RPI = Path(__file__).resolve().parents[1] / "rpi"
sys.path.insert(0, str(RPI))

from application.borne import Borne, PaiementEnCours
from modeles.comptes import (
    ConflitTransaction, DemandePaiement, StatutOperation, TypeOperation,
)
from modules.gestion_comptes import ServiceComptes
from modules.lecteur_nfc_rfid import EvenementRFID
from outils import comptes as outil_comptes, simuler_t04
from stockage import comptes_csv as stockage
from test_rfid_integration import BancSimule, BADGE_A, BADGE_B, BADGE_C

JASON, LUCIA, INCONNU = "11008827F9", "1100823734", "1100880F2D"


class BancComptes(unittest.TestCase):
    def setUp(self):
        self.temporaire = TemporaryDirectory()
        self.addCleanup(self.temporaire.cleanup)
        self.racine = Path(self.temporaire.name)
        self.modele = self.racine / "modele.csv"
        self.modele.write_bytes(stockage.CHEMIN_MODELE.read_bytes())
        self.dossier = self.racine / "actives"
        self.service = self.nouveau_service()
        self.service.lister_comptes()

    def nouveau_service(self):
        return ServiceComptes(stockage.DepotComptesCSV(self.dossier, self.modele))

    def solde(self, id_uart=JASON):
        return self.service.consulter_compte(id_uart).solde_centimes

    def lignes_journal(self):
        with (self.dossier / "operations.csv").open(newline="") as fichier:
            return list(csv.DictReader(fichier))

    def modifier_journal(self, lignes):
        with (self.dossier / "operations.csv").open("w", newline="") as fichier:
            auteur = csv.DictWriter(fichier, fieldnames=stockage.CHAMPS_OPERATIONS)
            auteur.writeheader()
            auteur.writerows(lignes)


class TestsServiceComptes(BancComptes):
    def test_consultation_conserve_les_deux_comptes_et_le_modele(self):
        self.assertEqual(set(self.service.lister_comptes()), {JASON, LUCIA})
        self.assertEqual(self.service.consulter_compte(JASON).nom, "Jason Duval")
        self.assertEqual(self.service.consulter_compte(LUCIA).solde_affiche, "20,00 $")
        self.assertIsNone(self.service.consulter_compte(INCONNU))
        self.assertIsNone(self.service.consulter_compte("12008827F9"))
        self.assertEqual(self.lignes_journal(), [])
        self.assertEqual(self.modele.read_bytes(), stockage.CHEMIN_MODELE.read_bytes())

    def test_paiement_credit_refus_et_redemarrage(self):
        paiement = self.service.payer("p-1", JASON, 500)
        self.assertEqual((paiement.statut, paiement.solde_apres_centimes),
                         (StatutOperation.PAIE, 1500))
        refus = self.service.payer("p-2", JASON, 2500)
        self.assertEqual(refus.statut, StatutOperation.SOLDE_INSUFFISANT)
        self.assertFalse(refus.succes)
        self.assertEqual(self.solde(), 1500)  # Pas de debit partiel.
        credit = self.service.crediter("c-1", JASON, 1000)
        self.assertEqual((credit.statut, credit.solde_apres_centimes),
                         (StatutOperation.CREDITE, 2500))
        self.assertEqual(self.nouveau_service().consulter_compte(JASON).solde_centimes, 2500)
        self.assertEqual(self.solde(LUCIA), 2000)
        self.assertEqual(len(self.lignes_journal()), 3)

    def test_somme_exacte_et_facture_nulle(self):
        self.assertTrue(self.service.payer("gratuit", JASON, 0).succes)
        self.assertEqual(self.solde(), 2000)
        self.assertTrue(self.service.payer("total", JASON, 2000).succes)
        self.assertEqual(self.solde(), 0)
        self.assertTrue(self.service.payer("gratuit-2", JASON, 0).succes)
        self.assertEqual(self.service.payer("trop", JASON, 1).statut,
                         StatutOperation.SOLDE_INSUFFISANT)

    def test_compte_inconnu_refuse_paiement_et_credit_sans_creation(self):
        for action, reference in ((self.service.payer, "p"), (self.service.crediter, "c")):
            resultat = action(reference, INCONNU, 500)
            self.assertEqual(resultat.statut, StatutOperation.COMPTE_INCONNU)
            self.assertIsNone(resultat.solde_avant_centimes)
            self.assertIsNone(resultat.solde_apres_centimes)
        self.assertEqual(len(self.service.lister_comptes()), 2)
        self.assertEqual(self.solde(), 2000)
        self.assertEqual(len(self.lignes_journal()), 2)

    def test_repetition_paiement_apres_redemarrage_ne_debite_pas(self):
        original = self.service.payer("p-unique", JASON.lower(), 500)
        self.service.crediter("c-suivant", JASON, 200)
        resultat = self.nouveau_service().payer("p-unique", JASON, 500)
        self.assertEqual(resultat, replace(original, deja_traitee=True))
        self.assertEqual(resultat.solde_apres_centimes, 1500)  # Recu historique.
        self.assertEqual(self.solde(), 1700)  # Solde courant.
        self.assertEqual(len(self.lignes_journal()), 2)

    def test_repetition_credit_ne_recharge_pas_deux_fois(self):
        self.service.crediter("credit-unique", LUCIA, 300)
        resultat = self.nouveau_service().crediter("credit-unique", LUCIA, 300)
        self.assertTrue(resultat.deja_traitee)
        self.assertEqual(self.solde(LUCIA), 2300)
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_refus_est_definitif_pour_cet_id_meme_apres_credit(self):
        self.service.payer("refus", JASON, 2500)
        self.service.crediter("recharge", JASON, 500)
        self.assertEqual(self.nouveau_service().payer("refus", JASON, 2500).statut,
                         StatutOperation.SOLDE_INSUFFISANT)
        self.assertEqual(self.solde(), 2500)
        self.assertTrue(self.service.payer("nouvel-essai", JASON, 2500).succes)
        self.assertEqual(self.solde(), 0)

    def test_reutiliser_un_id_avec_autre_montant_carte_ou_type_est_interdit(self):
        self.service.payer("meme-id", JASON, 500)
        for action, badge, montant in (
            (self.service.payer, JASON, 600),
            (self.service.payer, LUCIA, 500),
            (self.service.crediter, JASON, 500),
        ):
            with self.subTest(action=action, badge=badge, montant=montant):
                with self.assertRaises(ConflitTransaction):
                    action("meme-id", badge, montant)
        self.assertEqual((self.solde(), self.solde(LUCIA)), (1500, 2000))
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_montants_et_identifiants_invalides_ne_touchent_pas_au_stockage(self):
        avant = (self.dossier / "operations.csv").read_bytes()
        for montant in (-1, 5.5, "500", True, None):
            with self.subTest(montant=montant), self.assertRaises(ValueError):
                self.service.payer("p", JASON, montant)
        for montant in (0, -1, False):
            with self.subTest(credit=montant), self.assertRaises(ValueError):
                self.service.crediter("c", JASON, montant)
        for reference in ("", "avec espace", "a\nb", "../p", "x" * 129, None):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                self.service.payer(reference, JASON, 500)
        for badge in (None, "", "008827F9", "11008827FZ", 123):
            with self.subTest(badge=badge), self.assertRaises(ValueError):
                self.service.payer("p", badge, 500)
        self.assertEqual((self.dossier / "operations.csv").read_bytes(), avant)
        self.assertEqual(self.solde(), 2000)

    def test_deux_services_concurrents_ne_perdent_pas_de_mouvement(self):
        barriere = Barrier(8)

        def payer(numero):
            service = self.nouveau_service()
            barriere.wait(timeout=5)
            return service.payer(f"p-{numero}", JASON, 700)

        with ThreadPoolExecutor(max_workers=8) as groupe:
            resultats = list(groupe.map(payer, range(8)))
        self.assertEqual(sum(r.succes for r in resultats), 2)
        self.assertEqual(self.solde(), 600)
        self.assertEqual(len(self.lignes_journal()), 8)

    def test_demandes_identiques_concurrentes_produisent_un_seul_debit(self):
        barriere = Barrier(8)

        def payer(_):
            service = self.nouveau_service()
            barriere.wait(timeout=5)
            return service.payer("unique", JASON, 500)

        with ThreadPoolExecutor(max_workers=8) as groupe:
            resultats = list(groupe.map(payer, range(8)))
        self.assertTrue(all(r.succes for r in resultats))
        self.assertEqual(sum(not r.deja_traitee for r in resultats), 1)
        self.assertEqual(self.solde(), 1500)
        self.assertEqual(len(self.lignes_journal()), 1)


class TestsStockage(BancComptes):
    def test_mise_a_jour_du_modele_ne_reinitialise_pas_les_soldes(self):
        self.service.payer("p", JASON, 500)
        self.modele.write_text("mauvais fichier de demonstration\n")
        self.assertEqual(self.nouveau_service().consulter_compte(JASON).solde_centimes, 1500)
        self.modele.unlink()
        self.assertEqual(self.nouveau_service().consulter_compte(LUCIA).solde_centimes, 2000)

    def test_echec_avant_remplacement_journal_ne_debite_pas(self):
        ancien = (self.dossier / "operations.csv").read_bytes()
        with patch.object(stockage.os, "replace", side_effect=OSError("disque indisponible")):
            with self.assertRaises(stockage.ErreurStockage):
                self.service.payer("p", JASON, 500)
        self.assertEqual((self.dossier / "operations.csv").read_bytes(), ancien)
        self.assertEqual(self.solde(), 2000)
        self.assertEqual(list(self.dossier.glob("*.tmp")), [])
        self.assertTrue(self.service.payer("p", JASON, 500).succes)
        self.assertEqual(self.solde(), 1500)

    def test_interruption_apres_journal_recupere_le_solde_sans_double_debit(self):
        with patch.object(stockage, "_ecrire_comptes", side_effect=OSError("interruption")):
            with self.assertRaisesRegex(stockage.ErreurStockage, "MEME ID"):
                self.service.payer("p", JASON, 500)
        self.assertEqual(stockage.charger_comptes(self.dossier / "comptes.csv")[JASON].solde_centimes, 2000)
        resultat = self.nouveau_service().payer("p", JASON, 500)
        self.assertTrue(resultat.deja_traitee)
        self.assertEqual(self.solde(), 1500)
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_incident_apres_rename_journal_retrouve_le_resultat(self):
        ecrire = stockage._ecrire_csv_atomique

        def incident(chemin, champs, lignes):
            ecrire(chemin, champs, lignes)
            if chemin.name == "operations.csv":
                raise OSError("confirmation interrompue")

        with patch.object(stockage, "_ecrire_csv_atomique", incident):
            with self.assertRaises(stockage.ErreurStockage):
                self.service.payer("p", JASON, 500)
        self.assertTrue(self.nouveau_service().payer("p", JASON, 500).deja_traitee)
        self.assertEqual(self.solde(), 1500)

    def test_initialisation_interrompue_peut_reprendre(self):
        dossier = self.racine / "nouveau"
        service = ServiceComptes(stockage.DepotComptesCSV(dossier, self.modele))
        with patch.object(stockage, "_ecrire_comptes", side_effect=OSError("interruption")):
            with self.assertRaises(stockage.ErreurStockage):
                service.lister_comptes()
        self.assertTrue((dossier / "operations.csv").exists())
        self.assertEqual(service.consulter_compte(JASON).solde_centimes, 2000)

    def test_journal_supprime_ne_recree_pas_un_historique_vide(self):
        self.service.payer("p", JASON, 500)
        (self.dossier / "operations.csv").unlink()
        with self.assertRaisesRegex(stockage.ErreurStockage, "Journal absent"):
            self.nouveau_service().payer("p", JASON, 500)
        self.assertFalse((self.dossier / "operations.csv").exists())

    def test_comptes_absents_avec_historique_ne_sont_pas_recrees(self):
        self.service.payer("p", JASON, 500)
        (self.dossier / "comptes.csv").unlink()
        with self.assertRaisesRegex(stockage.ErreurStockage, "comptes absent"):
            self.nouveau_service().lister_comptes()
        self.assertFalse((self.dossier / "comptes.csv").exists())

    def test_journal_incoherent_est_refuse(self):
        self.service.payer("p-1", JASON, 500)
        self.service.payer("p-2", JASON, 100)
        original = self.lignes_journal()
        cas = [
            [original[0], original[0]],
            [dict(original[0], solde_apres_centimes="1501"), original[1]],
            [original[0], dict(original[1], solde_avant_centimes="1600",
                               solde_apres_centimes="1500")],
            [dict(original[0], statut="CREDITE"), original[1]],
            [dict(original[0], date_utc="2026-11-24"), original[1]],
        ]
        for lignes in cas:
            with self.subTest(lignes=lignes):
                self.modifier_journal(lignes)
                with self.assertRaises(stockage.ErreurStockage):
                    self.nouveau_service().payer("nouveau", JASON, 100)
        self.modifier_journal(original)
        self.assertEqual(self.solde(), 1400)

    def test_modele_invalide_est_refuse_avant_initialisation(self):
        for contenu in (
            "autre,entete\n",
            "id_uart,nom,solde_centimes\n",
            f"id_uart,nom,solde_centimes\n{JASON},Jason,-1\n",
            f"id_uart,nom,solde_centimes\n{JASON},,2000\n",
            f"id_uart,nom,solde_centimes\n{JASON},Jason,20.0\n",
            f"id_uart,nom,solde_centimes\n{JASON},Jason,2000\n{JASON},Jason,2000\n",
        ):
            with self.subTest(contenu=contenu):
                self.modele.write_text(contenu)
                dossier = self.racine / "invalide"
                service = ServiceComptes(stockage.DepotComptesCSV(dossier, self.modele))
                with self.assertRaises(stockage.ErreurStockage):
                    service.lister_comptes()
                self.assertFalse((dossier / "operations.csv").exists())


class TestsBorne(BancComptes):
    def setUp(self):
        super().setUp()
        self.affichage = Mock()
        self.borne = Borne(self.service, self.affichage)

    def badge(self, id_uart=JASON, type_evenement="ACCEPTE"):
        self.borne.traiter_evenement(EvenementRFID(type_evenement, "essai", id_uart))

    def test_badge_seul_consulte_sans_payer(self):
        self.badge()
        self.assertEqual(self.solde(), 2000)
        self.assertEqual(self.borne.lire_resultats_paiement(), [])
        self.assertEqual(self.lignes_journal(), [])
        self.affichage.compte.assert_called_once()

    def test_seule_lecture_acceptee_paie_une_demande(self):
        self.borne.demander_paiement(DemandePaiement("p", 500))
        for evenement in ("INFO", "PRESENCE", "INVALIDE", "IGNORE", "RETRAIT"):
            self.badge(type_evenement=evenement)
        self.assertEqual(self.lignes_journal(), [])
        self.badge()
        self.badge()  # Plus de demande : consultation seule.
        resultats = self.borne.lire_resultats_paiement()
        self.assertEqual(len(resultats), 1)
        self.assertEqual(resultats[0].statut, StatutOperation.PAIE)
        self.assertEqual(self.solde(), 1500)
        self.assertEqual(self.borne.lire_resultats_paiement(), [])
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_demande_unique_en_attente_et_annulation_ciblee(self):
        self.borne.demander_paiement(DemandePaiement("p", 500))
        self.borne.demander_paiement(DemandePaiement("p", 500))
        with self.assertRaises(PaiementEnCours):
            self.borne.demander_paiement(DemandePaiement("autre", 500))
        with self.assertRaises(ConflitTransaction):
            self.borne.demander_paiement(DemandePaiement("p", 600))
        self.assertFalse(self.borne.annuler_paiement("autre"))
        self.assertTrue(self.borne.annuler_paiement("p"))
        self.assertFalse(self.borne.annuler_paiement("p"))
        self.badge()
        self.assertEqual(self.lignes_journal(), [])

    def test_refus_termine_la_tentative_et_autre_carte_exige_nouvelle_demande(self):
        self.borne.demander_paiement(DemandePaiement("refus", 500))
        self.badge(INCONNU)
        self.badge(JASON)
        self.assertEqual(self.solde(), 2000)
        self.assertEqual(self.borne.lire_resultats_paiement()[0].statut,
                         StatutOperation.COMPTE_INCONNU)
        self.borne.demander_paiement(DemandePaiement("refus", 500))
        self.assertTrue(self.borne.lire_resultats_paiement()[0].deja_traitee)
        self.borne.demander_paiement(DemandePaiement("nouveau", 500))
        self.badge(JASON)
        self.assertEqual(self.solde(), 1500)

    def test_reprise_t04_apres_redemarrage_renvoie_le_resultat_sans_badge(self):
        demande = DemandePaiement("p", 500)
        self.borne.demander_paiement(demande)
        self.badge()
        original = self.borne.lire_resultats_paiement()[0]
        nouvelle = Borne(self.nouveau_service(), Mock())
        nouvelle.demander_paiement(demande)
        self.assertEqual(nouvelle.lire_resultats_paiement(),
                         [replace(original, deja_traitee=True)])
        self.assertEqual(self.solde(), 1500)

    def test_collision_avec_paiement_different_ou_credit(self):
        self.service.payer("p", JASON, 500)
        self.service.crediter("c", JASON, 100)
        for demande in (DemandePaiement("p", 600), DemandePaiement("c", 100)):
            with self.subTest(demande=demande), self.assertRaises(ConflitTransaction):
                self.borne.demander_paiement(demande)
        self.assertEqual(self.borne.lire_resultats_paiement(), [])
        self.assertEqual(self.solde(), 1600)

    def test_erreur_stockage_ne_publie_pas_un_succes_ou_un_refus(self):
        self.borne.demander_paiement(DemandePaiement("p", 500))
        with patch.object(stockage, "_ecrire_comptes", side_effect=OSError("interruption")):
            with self.assertRaises(stockage.ErreurStockage):
                self.badge()
        self.assertEqual(self.borne.lire_resultats_paiement(), [])
        self.badge()  # Meme ID et meme carte : reprise sans nouveau debit.
        resultat = self.borne.lire_resultats_paiement()[0]
        self.assertTrue(resultat.deja_traitee)
        self.assertEqual(self.solde(), 1500)


class TestsOutils(BancComptes):
    def test_aide_des_points_entree_sans_bibliotheques_materielles(self):
        for script in ("main.py", "outils/comptes.py", "outils/simuler_t04.py"):
            with self.subTest(script=script):
                resultat = subprocess.run(
                    [sys.executable, "-B", str(RPI / script), "--help"],
                    cwd=self.racine, capture_output=True, text=True,
                )
                self.assertEqual(resultat.returncode, 0, resultat.stderr)

    def test_outil_credit_utilise_le_service_et_le_meme_journal(self):
        args = ["--donnees", str(self.dossier), "crediter",
                "--id-transaction", "credit-cli", "--id-uart", JASON,
                "--montant-centimes", "500"]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(outil_comptes.main(args), 0)
            self.assertEqual(outil_comptes.main(args), 0)
        self.assertEqual(self.solde(), 2500)
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_simulateur_renvoie_resultat_existant_sans_acces_gpio(self):
        self.service.payer("p", JASON, 500)
        with patch.object(simuler_t04.rfid, "LecteurRFID",
                          side_effect=AssertionError("GPIO ne doit pas etre ouvert")), \
             redirect_stdout(io.StringIO()) as sortie:
            code = simuler_t04.main(["--donnees", str(self.dossier), "--id-transaction", "p",
                                     "--montant-centimes", "500"])
        self.assertEqual(code, 0)
        self.assertIn("aucun nouveau mouvement", sortie.getvalue())
        self.assertEqual(self.solde(), 1500)

    def test_simulateur_parcours_complet_vrai_lecteur_et_vrais_csv(self):
        for numero, (trame, montant, code_attendu, statut) in enumerate((
            (BADGE_B, 500, 0, "PAIE"),
            (BADGE_A, 2500, 2, "SOLDE_INSUFFISANT"),
            (BADGE_C, 500, 2, "COMPTE_INCONNU"),
        )):
            with self.subTest(statut=statut), ExitStack() as ressources:
                banc = BancSimule()
                banc.installer(ressources)

                def avancer(_):
                    banc.maintenant = 1
                    banc.rng.definir(True)
                    banc.uart.tampon.extend(trame)

                ressources.enter_context(patch("application.borne.time.sleep", avancer))
                sortie = ressources.enter_context(redirect_stdout(io.StringIO()))
                erreur = ressources.enter_context(redirect_stderr(io.StringIO()))
                code = simuler_t04.main([
                    "--donnees", str(self.dossier), "--id-transaction", f"t04-{numero}",
                    "--montant-centimes", str(montant),
                ])
                self.assertEqual(code, code_attendu, erreur.getvalue())
                self.assertIn(f"BORNE | {statut} |", sortie.getvalue())
                self.assertEqual(banc.fermetures, ["uart", "rng", "fabrique"])
        self.assertEqual(self.solde(), 1500)
        self.assertEqual(self.solde(LUCIA), 2000)
        self.assertEqual(len(self.lignes_journal()), 3)


if __name__ == "__main__":
    unittest.main()
