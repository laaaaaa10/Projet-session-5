"""T12 financier : vrai T02/CSV temporaires ; horloge, RFID et T04 simulés."""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

RPI = Path(__file__).resolve().parents[1] / "rpi"
sys.path.insert(0, str(RPI))

from api.retrait import StatutRetrait
from application.borne import Borne
from exemples.facturation_retrait_simulee import FacturationRetraitSimulee
from modeles.comptes import StatutOperation, TypeOperation
from modules.demande_retrait import EtapeDemandeRetrait as E, GestionDemandeRetrait
from modules.gestion_comptes import ServiceComptes
from modules.lecteur_nfc_rfid import EvenementRFID
from stockage.comptes_csv import DepotComptesCSV

CARTE_A, CARTE_B = "0000000001", "0000000002"


class Horloge:
    temps = 75.0

    def __call__(self):
        return self.temps


class BancRetrait(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="esa-test-t12-")
        self.addCleanup(self.temp.cleanup)
        self.racine = Path(self.temp.name)
        modele = self.racine / "modele.csv"
        modele.write_text("id_uart,nom,solde_centimes\n"
                          f"{CARTE_A},Carte A,150\n{CARTE_B},Carte B,500\n", encoding="utf-8")
        self.comptes = ServiceComptes(DepotComptesCSV(self.racine / "comptes", modele))
        self.borne = Borne(self.comptes, Mock())
        self.horloge = Horloge()
        self.t04 = FacturationRetraitSimulee(self.borne, horloge=self.horloge)
        self.t04.ajouter_transaction(123456, 10, depose_a=0)
        self.t04.ajouter_transaction(654321, 11, depose_a=0)
        self.journal = self.racine / "retraits.sqlite3"
        self.t12 = GestionDemandeRetrait(self.t04, self.journal)
        self.addCleanup(lambda: self.t12.fermer())
        self.t12.autoriser_nouvelles(True)

    def commencer(self, identifiant="retrait-1", numero=123456):
        self.assertTrue(self.t12.demander_retrait(numero, id_demande=identifiant))
        self.assertTrue(self.t12.confirmer_retrait_et_figer_montant(identifiant))

    def badge(self, carte=CARTE_B):
        admis = self.t04.avant_presentation()
        if admis:
            try:
                self.borne.traiter_evenement(EvenementRFID("ACCEPTE", "Banc T12", carte))
            finally:
                self.t04.apres_presentation()
        self.t04.actualiser()
        self.t12.mettre_a_jour()
        return admis

    def solde(self, carte):
        return self.comptes.consulter_compte(carte).solde_centimes


class TestsPaiementT12(BancRetrait):
    def test_lecture_billet_ne_gele_ni_ne_debite(self):
        self.assertTrue(self.t12.demander_retrait(123456, id_demande="r"))
        self.assertEqual(self.t12.etape, E.DEMANDE)
        self.assertEqual(self.t04.gels, 0)
        self.assertEqual(self.solde(CARTE_B), 500)
        self.assertFalse(self.t12.paiement_valide)

    def test_paiement_complet_et_repetition_sans_second_debit(self):
        self.commencer()
        self.assertFalse(self.t12.paiement_valide)
        self.assertTrue(self.badge())
        self.assertEqual(self.t12.etape, E.PAYE)
        self.assertEqual(self.solde(CARTE_B), 300)
        for _ in range(3):
            self.assertTrue(self.t12.demander_retrait(123456, id_demande="retrait-1"))
            self.assertTrue(self.t12.confirmer_retrait_et_figer_montant("retrait-1"))
            self.t12.mettre_a_jour()
            self.assertFalse(self.badge())
        self.assertEqual(self.solde(CARTE_B), 300)
        self.assertEqual(self.t04.gels, 1)

    def test_carte_insuffisante_puis_autre_carte_sans_cumul(self):
        self.commencer()
        premier = self.t04.dossiers["retrait-1"]["id_paiement"]
        self.badge(CARTE_A)
        self.assertEqual(self.t12.etape, E.ATTENTE)
        self.assertEqual(self.solde(CARTE_A), 150)
        self.assertNotEqual(self.t04.dossiers["retrait-1"]["id_paiement"], premier)
        self.badge(CARTE_B)
        self.assertTrue(self.t12.paiement_valide)
        self.assertEqual((self.solde(CARTE_A), self.solde(CARTE_B)), (150, 300))
        self.assertEqual(self.t04.gels, 1)

    def test_carte_inconnue_ne_valide_pas_le_paiement(self):
        self.commencer()
        self.badge("FFFFFFFFFF")
        self.assertEqual(self.t12.etape, E.ATTENTE)
        self.assertEqual(self.solde(CARTE_B), 500)

    def test_59999_secondes_paiement_valide(self):
        self.commencer()
        self.horloge.temps += 59.999
        self.assertTrue(self.badge())
        self.assertTrue(self.t12.paiement_valide)

    def test_a_60_secondes_et_apres_aucun_debit(self):
        self.commencer()
        self.horloge.temps += 60
        self.assertFalse(self.badge())
        self.assertEqual(self.t12.etape, E.EXPIRE)
        self.horloge.temps += 10
        self.assertFalse(self.badge())
        self.assertEqual(self.solde(CARTE_B), 500)

    def test_refus_et_retransmissions_ne_prolongent_pas_le_delai(self):
        self.commencer()
        f = self.t04.consulter_retrait("retrait-1").fenetre
        self.horloge.temps += 59
        self.badge(CARTE_A)
        self.t12.confirmer_retrait_et_figer_montant("retrait-1")
        self.assertEqual(self.t04.figer_montant(123456, "retrait-1").fenetre, f)
        self.horloge.temps += 1
        self.assertFalse(self.badge())
        self.assertEqual(self.solde(CARTE_A), 150)

    def test_expiration_recalcul_depuis_depot_sans_minute_gratuite(self):
        self.commencer()
        self.assertEqual(self.t04.consulter_retrait("retrait-1").fenetre.montant_centimes, 200)
        self.horloge.temps = 135
        self.t12.mettre_a_jour()
        self.assertEqual(self.t12.etape, E.EXPIRE)
        self.commencer("retrait-2")
        self.assertEqual(self.t04.consulter_retrait("retrait-2").fenetre.montant_centimes, 300)
        self.assertEqual(self.t04.transactions[123456][1], 0)

    def test_un_ancien_id_expire_ne_rouvre_pas_de_fenetre(self):
        self.commencer()
        self.horloge.temps += 60
        self.t12.mettre_a_jour()
        self.assertTrue(self.t12.demander_retrait(123456, id_demande="retrait-1"))
        self.assertFalse(self.t12.confirmer_retrait_et_figer_montant("retrait-1"))
        self.assertEqual(self.t04.gels, 1)

    def test_ancien_evenement_ne_confirme_pas_la_nouvelle_demande(self):
        self.commencer()
        self.assertTrue(self.t12.annuler("retrait-1"))
        self.assertTrue(self.t12.demander_retrait(654321, id_demande="retrait-2"))
        self.assertTrue(self.t12.demander_retrait(123456, id_demande="retrait-1"))
        self.assertFalse(self.t12.confirmer_retrait_et_figer_montant("retrait-1"))
        self.assertFalse(self.t12.annuler("retrait-1"))
        self.assertEqual(self.t12.id_demande, "retrait-2")
        self.assertEqual(self.t12.etape, E.DEMANDE)

    def test_deux_demandes_et_id_reutilise_sont_refuses(self):
        self.commencer()
        self.assertFalse(self.t12.demander_retrait(654321, id_demande="autre"))
        with self.assertRaises(ValueError):
            self.t12.demander_retrait(654321, id_demande="retrait-1")
        self.assertEqual(self.t04.gels, 1)

    def test_transaction_inconnue_et_identifiants_invalides(self):
        self.assertFalse(self.t12.demander_retrait(123, id_demande="inconnu"))
        for numero in (True, -1, 1_000_000, "123456"):
            with self.subTest(numero=numero), self.assertRaises(ValueError):
                self.t12.demander_retrait(numero, id_demande="r")
        with self.assertRaises(ValueError):
            self.t12.demander_retrait(123456, id_demande="")
        self.assertEqual(self.t04.gels, 0)

    def test_montant_nul_exige_quand_meme_une_carte_connue(self):
        self.t04.ajouter_transaction(333333, 1, depose_a=75, tarif_centimes=0)
        self.commencer(numero=333333)
        self.t12.mettre_a_jour()
        self.assertFalse(self.t12.paiement_valide)
        self.badge("FFFFFFFFFF")
        self.assertFalse(self.t12.paiement_valide)
        self.badge(CARTE_B)
        self.assertTrue(self.t12.paiement_valide)
        self.assertEqual(self.solde(CARTE_B), 500)

    def test_annulation_de_l_attente_empeche_le_debit(self):
        self.commencer()
        self.assertTrue(self.t12.annuler("retrait-1"))
        self.assertFalse(self.badge())
        self.assertEqual(self.solde(CARTE_B), 500)

    def test_annulation_concurrente_preserve_paiement_deja_enregistre(self):
        self.commencer()
        self.assertTrue(self.t04.avant_presentation())
        self.borne.traiter_evenement(EvenementRFID("ACCEPTE", "banc", CARTE_B))
        self.t04.apres_presentation()
        # Notification pas encore traitée par T04 ; reçu déjà durable chez T02.
        self.assertFalse(self.t12.annuler("retrait-1"))
        self.assertTrue(self.t12.paiement_valide)
        self.assertEqual(self.solde(CARTE_B), 300)

    def test_paiement_anterieur_retrouve_apres_echeance(self):
        self.commencer()
        self.horloge.temps += 59.9
        self.assertTrue(self.t04.avant_presentation())
        self.borne.traiter_evenement(EvenementRFID("ACCEPTE", "banc", CARTE_B))
        self.t04.apres_presentation()
        self.horloge.temps += 2
        self.t12.mettre_a_jour()
        self.assertTrue(self.t12.paiement_valide)
        self.assertEqual(self.solde(CARTE_B), 300)

    def test_debit_termine_apres_echeance_exige_reconciliation(self):
        self.commencer()
        self.horloge.temps += 59.9
        self.assertTrue(self.t04.avant_presentation())
        self.borne.traiter_evenement(EvenementRFID("ACCEPTE", "banc", CARTE_B))
        self.horloge.temps += 0.2  # Appel de paiement terminé après l'échéance.
        self.t04.apres_presentation()
        self.t12.mettre_a_jour()
        self.assertEqual(self.t12.etape, E.INCERTAIN)
        self.assertFalse(self.badge())
        self.assertEqual(self.solde(CARTE_B), 300)  # Aucun faux remboursement.

    def test_debit_hors_admission_du_banc_reste_incertain(self):
        self.commencer()
        # Mauvais raccordement volontaire : T02 appelé sans le garde T04.
        self.borne.traiter_evenement(EvenementRFID("ACCEPTE", "banc", CARTE_B))
        self.t12.mettre_a_jour()
        self.assertEqual(self.t12.etape, E.INCERTAIN)
        self.assertFalse(self.badge())
        self.assertEqual(self.solde(CARTE_B), 300)
        self.assertEqual(self.t04.dossiers["retrait-1"]["tentative"], 1)

    def test_reponse_de_gel_perdue_est_retrouvee_sans_second_gel(self):
        self.t12.demander_retrait(123456, id_demande="r")
        original = self.t04.figer_montant
        def perdu(*args):
            original(*args)
            raise OSError("Réponse perdue")
        with patch.object(self.t04, "figer_montant", side_effect=perdu):
            self.assertFalse(self.t12.confirmer_retrait_et_figer_montant("r"))
        self.assertEqual(self.t12.etape, E.INCERTAIN)
        self.t12.mettre_a_jour()
        self.assertEqual(self.t12.etape, E.ATTENTE)
        self.assertEqual(self.t04.gels, 1)

    def test_erreur_de_stockage_ne_signifie_pas_refus_ni_autre_debit(self):
        self.commencer()
        with patch.object(self.borne, "retrouver_resultat_paiement", side_effect=OSError("disque")):
            self.t12.mettre_a_jour()
            self.assertEqual(self.t12.etape, E.INCERTAIN)
            self.assertFalse(self.badge())
        self.assertEqual(self.solde(CARTE_B), 500)
        self.t12.mettre_a_jour()
        # Sans preuve d'absence d'effet, le double ne crée pas une nouvelle tentative.
        self.assertEqual(self.t04.dossiers["retrait-1"]["tentative"], 1)

    def test_echec_journal_avant_gel_ne_contacte_pas_t04(self):
        self.t12.demander_retrait(123456, id_demande="r")
        with patch.object(self.t12, "_enregistrer", side_effect=OSError("journal indisponible")):
            with self.assertRaises(OSError):
                self.t12.confirmer_retrait_et_figer_montant("r")
        self.assertEqual(self.t04.gels, 0)

    def test_redemarrage_interrompt_sans_rejouer(self):
        self.commencer()
        self.t12.fermer()
        with patch.object(self.t04, "figer_montant", wraps=self.t04.figer_montant) as gel:
            self.t12 = GestionDemandeRetrait(self.t04, self.journal)
            self.t12.autoriser_nouvelles(True)
            self.t12.mettre_a_jour()
            self.assertEqual(self.t12.etape, E.INTERROMPU)
            self.assertFalse(self.t12.confirmer_retrait_et_figer_montant("retrait-1"))
            self.assertFalse(self.t12.demander_retrait(123456, id_demande="nouveau"))
            gel.assert_not_called()

    def test_redemarrage_apres_paiement_conserve_recu_sans_autorisation(self):
        self.commencer()
        self.badge()
        preuve = self.t12.instantane()["paiement"]
        self.t12.fermer()
        self.t12 = GestionDemandeRetrait(self.t04, self.journal)
        self.assertEqual(self.t12.etape, E.INTERROMPU)
        self.assertEqual(self.t12.instantane()["paiement"], preuve)
        self.assertFalse(self.t12.paiement_valide)
        self.assertEqual(self.solde(CARTE_B), 300)

    def test_arret_annule_attente_et_aucune_reprise_automatique(self):
        self.commencer()
        self.t12.arreter()
        self.assertFalse(self.badge())
        self.t12.autoriser_nouvelles(True)
        self.t12.mettre_a_jour()
        self.assertEqual(self.t12.etape, E.INTERROMPU)
        self.assertFalse(self.t12.confirmer_retrait_et_figer_montant("retrait-1"))
        self.assertEqual(self.solde(CARTE_B), 500)

    def test_interdiction_nouvelles_ne_rembourse_pas_paiement_valide(self):
        self.commencer()
        self.badge()
        self.t12.autoriser_nouvelles(False)
        self.assertFalse(self.t12.annuler("retrait-1"))
        self.assertTrue(self.t12.paiement_valide)
        self.assertEqual(self.solde(CARTE_B), 300)

    def test_nouvelles_interdites_et_confirmation_bloquee(self):
        self.t12.autoriser_nouvelles(False)
        self.assertFalse(self.t12.demander_retrait(123456, id_demande="r"))
        self.t12.autoriser_nouvelles(True)
        self.t12.demander_retrait(123456, id_demande="r")
        self.t12.autoriser_nouvelles(False)
        self.assertFalse(self.t12.confirmer_retrait_et_figer_montant("r"))
        self.assertEqual(self.t04.gels, 0)

    def test_t04_refuse_un_autre_id_pour_transaction_deja_payee(self):
        self.commencer()
        self.badge()
        with self.assertRaises(ValueError):
            self.t04.figer_montant(123456, "autre-retrait")
        self.assertEqual(self.solde(CARTE_B), 300)


class TestsReponsesT04(BancRetrait):
    def test_reponse_incoherente_nautorise_pas_le_retrait(self):
        self.commencer()
        suivi = self.t04.consulter_retrait("retrait-1")
        mauvaises = [
            replace(suivi, fenetre=replace(suivi.fenetre, id_retrait="autre")),
            replace(suivi, fenetre=replace(suivi.fenetre, montant_centimes=201)),
            replace(suivi, fenetre=replace(suivi.fenetre, expire_a=200)),
            replace(suivi, statut=StatutRetrait.PAYE),
            None,
        ]
        for reponse in mauvaises:
            with self.subTest(reponse=reponse), patch.object(self.t04, "consulter_retrait", return_value=reponse):
                self.t12.mettre_a_jour()
                self.assertEqual(self.t12.etape, E.INCERTAIN)
                self.assertFalse(self.t12.paiement_valide)

    def test_paiement_partiel_hors_delai_ou_mauvais_type_refuse(self):
        self.commencer()
        self.t04.avant_presentation()
        self.borne.traiter_evenement(EvenementRFID("ACCEPTE", "banc", CARTE_B))
        self.t04.apres_presentation()
        suivi = self.t04.consulter_retrait("retrait-1")
        for reponse in (
            replace(suivi, paiement=replace(suivi.paiement, montant_centimes=100)),
            replace(suivi, paiement=replace(suivi.paiement, montant_centimes=200.0)),
            replace(suivi, paiement=replace(suivi.paiement, type_operation=TypeOperation.CREDIT)),
            replace(suivi, paiement=replace(suivi.paiement, statut=StatutOperation.SOLDE_INSUFFISANT)),
            replace(suivi, paiement=replace(suivi.paiement, solde_apres_centimes=400)),
            replace(suivi, valide_a=suivi.fenetre.expire_a),
            replace(suivi, valide_a=float("nan")),
        ):
            with self.subTest(reponse=reponse), patch.object(self.t04, "consulter_retrait", return_value=reponse):
                self.t12.mettre_a_jour()
                self.assertEqual(self.t12.etape, E.INCERTAIN)

    def test_import_sans_qt_can_lecteur_ni_csv(self):
        code = ("import sys\n"
                "sys.path.insert(0, sys.argv[1])\n"
                "from api.retrait import InterfaceFacturationRetrait\n"
                "from modules.demande_retrait import GestionDemandeRetrait\n"
                "for nom in ('can', 'PyQt6', 'serial', 'lgpio', 'stockage.comptes_csv', "
                "'modules.lecteur_nfc_rfid'):\n"
                "    assert nom not in sys.modules, nom\n")
        resultat = subprocess.run([sys.executable, "-B", "-c", code, str(RPI)],
                                  capture_output=True, text=True)
        self.assertEqual(resultat.returncode, 0, resultat.stderr)


if __name__ == "__main__":
    unittest.main()
