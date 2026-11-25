"""Vrai Qt hors ecran, vrai service CSV et vrai lecteur avec UART/GPIO simules.

Si PyQt6 est absent, seule cette suite optionnelle est ignoree.
"""

from contextlib import ExitStack
import os
from pathlib import Path
import sys
from threading import Event, get_ident
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RPI = Path(__file__).resolve().parents[1] / "rpi"
sys.path.insert(0, str(RPI))

from application import integration_t03, integration_t04, integration_t13
from modeles.comptes import DemandePaiement, StatutOperation
from modules.gestion_comptes import ServiceComptes
from stockage import comptes_csv as stockage
from test_comptes_transactions import BancComptes, JASON, LUCIA, INCONNU
from test_rfid_integration import BancSimule, BADGE_B

try:
    from PyQt6.QtCore import QObject, QElapsedTimer, QThread, QTimer, pyqtSlot
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    from interface.qt.pont_t02 import PontT02Qt
    from interface.qt.fenetre_demo import FenetreDemoT02
    QT_DISPONIBLE = True
except ModuleNotFoundError as erreur:
    if erreur.name != "PyQt6":
        raise
    QT_DISPONIBLE = False


if QT_DISPONIBLE:
    class Recepteur(QObject):
        def __init__(self):
            super().__init__()
            self.comptes = self.identifications = None
            self.reponses, self.erreurs, self.paiements, self.lectures, self.avertissements = {}, [], [], [], []
            self.threads = []

        @pyqtSlot(object)
        def pret(self, comptes):
            self.comptes = comptes
            self.threads.append(QThread.currentThread() == QApplication.instance().thread())

        @pyqtSlot(str, str, object)
        def reponse(self, reference, action, resultat):
            self.reponses[reference] = (action, resultat)
            self.threads.append(QThread.currentThread() == QApplication.instance().thread())

        @pyqtSlot(object)
        def paiement(self, resultat):
            self.paiements.append(resultat)
            self.threads.append(QThread.currentThread() == QApplication.instance().thread())


@unittest.skipUnless(QT_DISPONIBLE, "PyQt6 optionnel absent : installer requirements-qt.txt pour tester l'UI")
class TestsInterfaceGraphique(BancComptes):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        super().setUp()
        self.ponts = []
        self.fenetres = []
        self.addCleanup(self.fermer_tout)

    def attendre(self, condition, message="Evenement Qt attendu", delai=4000):
        horloge = QElapsedTimer()
        horloge.start()
        while not condition() and horloge.elapsed() < delai:
            QTest.qWait(5)
        self.assertTrue(condition(), message)

    def fermer_tout(self):
        for fenetre in self.fenetres:
            fenetre.close()
        for pont, _ in self.ponts:
            pont.arreter()
        self.attendre(lambda: all(not p.en_cours for p, _ in self.ponts), "Threads non termines")
        for fenetre in self.fenetres:
            fenetre.close()
        self.app.processEvents()

    def nouveau_pont(self, **options):
        pont = PontT02Qt(self.dossier, **options)
        recepteur = Recepteur()
        pont.pret.connect(recepteur.pret)
        pont.reponse.connect(recepteur.reponse)
        pont.resultat_paiement.connect(recepteur.paiement)
        pont.erreur.connect(recepteur.erreurs.append)
        pont.carte_lue.connect(recepteur.lectures.append)
        pont.avertissement.connect(recepteur.avertissements.append)
        self.ponts.append((pont, recepteur))
        return pont, recepteur

    def ouvrir(self, **options):
        options.setdefault("simulation", True)
        pont, recepteur = self.nouveau_pont(**options)
        pont.demarrer()
        self.attendre(lambda: recepteur.comptes is not None or bool(recepteur.erreurs))
        self.assertEqual(recepteur.erreurs, [])
        return pont, recepteur

    def reponse(self, recepteur, reference):
        self.attendre(lambda: reference in recepteur.reponses or
                      any(e.reference == reference for e in recepteur.erreurs))
        self.assertIn(reference, recepteur.reponses, str(recepteur.erreurs))
        return recepteur.reponses[reference][1]

    def paiement(self, pont, recepteur, reference, montant, carte):
        nombre = len(recepteur.paiements)
        self.reponse(recepteur, pont.demander_paiement(DemandePaiement(reference, montant)))
        self.reponse(recepteur, pont.simuler_badge(carte))
        self.attendre(lambda: len(recepteur.paiements) > nombre)
        return recepteur.paiements[-1]

    def test_csv_deportes_et_retours_dans_thread_graphique(self):
        main_thread = get_ident()
        acces_disque = []
        lire = stockage.charger_comptes

        def lire_trace(*args, **kwargs):
            acces_disque.append(get_ident())
            return lire(*args, **kwargs)

        with patch.object(stockage, "charger_comptes", lire_trace):
            pont, r = self.ouvrir()
            self.assertEqual(self.reponse(r, pont.consulter_solde(JASON)), 2000)
            credit = self.reponse(r, pont.ajouter_credit("c", JASON, 500))
            self.assertEqual(credit.solde_apres_centimes, 2500)
            self.assertEqual(self.paiement(pont, r, "p", 500, JASON).statut, StatutOperation.PAIE)
            pont.arreter()
            self.attendre(lambda: not pont.en_cours)
        self.assertTrue(acces_disque)
        self.assertTrue(all(t != main_thread for t in acces_disque))
        self.assertTrue(all(r.threads))

    def test_credit_paiement_refus_et_reprises_apres_redemarrage(self):
        pont, r = self.ouvrir()
        self.reponse(r, pont.ajouter_credit("c", JASON, 500))
        self.assertTrue(self.reponse(r, pont.ajouter_credit("c", JASON, 500)).deja_traitee)
        self.assertEqual(self.paiement(pont, r, "p", 2200, JASON).solde_apres_centimes, 300)
        self.assertEqual(self.paiement(pont, r, "refus", 2200, LUCIA).statut, StatutOperation.SOLDE_INSUFFISANT)
        self.assertEqual(self.paiement(pont, r, "inconnu", 500, INCONNU).statut, StatutOperation.COMPTE_INCONNU)
        self.assertEqual(r.lectures, [])  # Les cartes de paiement ne deviennent pas des identifications.
        pont.arreter()
        self.attendre(lambda: not pont.en_cours)
        pont, r = self.ouvrir()
        self.assertTrue(self.reponse(r, pont.ajouter_credit("c", JASON, 500)).deja_traitee)
        self.reponse(r, pont.demander_paiement(DemandePaiement("p", 2200)))
        self.attendre(lambda: len(r.paiements) == 1)
        self.assertTrue(r.paiements[0].deja_traitee)
        self.assertEqual(self.reponse(r, pont.lister_soldes()), {JASON: 300, LUCIA: 2000})
        self.assertEqual(len(self.lignes_journal()), 4)

    def test_erreur_de_commande_corrigeable_sans_arreter_le_lecteur(self):
        pont, r = self.ouvrir()
        reference = pont.ajouter_credit("c", JASON, True)
        self.attendre(lambda: bool(r.erreurs))
        self.assertEqual((r.erreurs[0].reference, r.erreurs[0].type_erreur, r.erreurs[0].fatal),
                         (reference, "ValueError", False))
        self.assertTrue(pont.en_cours)
        self.assertEqual(self.lignes_journal(), [])
        self.assertTrue(self.reponse(r, pont.ajouter_credit("c", JASON, 500)).succes)
        reference = pont.ajouter_credit("c", JASON, 600)
        self.attendre(lambda: len(r.erreurs) == 2)
        self.assertEqual(r.erreurs[-1].type_erreur, "ConflitTransaction")
        self.assertNotIn(reference, r.reponses)
        self.assertEqual(self.reponse(r, pont.consulter_solde(JASON)), 2500)

    def test_credit_incertain_et_avertissement_recuperation_arrivent_dans_ui(self):
        pont, r = self.ouvrir()
        with patch.object(stockage, "_ecrire_comptes", side_effect=OSError("interruption")):
            reference = pont.ajouter_credit("c", JASON, 500)
            self.attendre(lambda: bool(r.erreurs))
        self.assertNotIn(reference, r.reponses)
        self.assertEqual(r.erreurs[0].type_erreur, "ErreurStockage")
        credit = self.reponse(r, pont.ajouter_credit("c", JASON, 500))
        self.assertTrue(credit.deja_traitee)
        self.attendre(lambda: bool(r.avertissements))
        self.assertIn("2000 -> 2500 centimes", r.avertissements[0])
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_vrai_lecteur_filtre_carte_maintenue_et_libere_gpio(self):
        banc = BancSimule()
        with ExitStack() as ressources:
            banc.installer(ressources)
            pont, r = self.ouvrir(simulation=False)
            banc.maintenant = 1
            banc.rng.definir(True)
            banc.uart.tampon.extend(BADGE_B + BADGE_B)
            self.attendre(lambda: len(r.lectures) == 1)
            self.assertEqual(r.lectures[0].id_uart, JASON)
            self.assertEqual(self.reponse(r, pont.lister_soldes()), {JASON: 2000, LUCIA: 2000})
            self.assertEqual(len(r.lectures), 1)
            reference = pont.simuler_badge(JASON)
            self.attendre(lambda: any(e.reference == reference for e in r.erreurs))
            self.assertEqual(r.erreurs[-1].type_erreur, "ValueError")
            pont.arreter()
            self.attendre(lambda: not pont.en_cours)
        self.assertEqual(banc.chips, [0])
        self.assertEqual(banc.fermetures, ["uart", "rng", "fabrique"])

    def test_echec_ouverture_uart_libere_gpio_et_thread(self):
        banc = BancSimule()
        banc.erreur_ouverture = True
        with ExitStack() as ressources:
            banc.installer(ressources)
            pont, r = self.nouveau_pont(simulation=False)
            pont.demarrer()
            self.attendre(lambda: not pont.en_cours)
        self.assertIsNone(r.comptes)
        self.assertEqual((r.erreurs[0].action, r.erreurs[0].fatal), ("demarrage", True))
        self.assertEqual(banc.fermetures, ["rng", "fabrique"])

    def test_deconnexion_uart_signalee_sans_faux_paiement(self):
        banc = BancSimule()
        with ExitStack() as ressources:
            banc.installer(ressources)
            pont, r = self.ouvrir(simulation=False)
            self.reponse(r, pont.demander_paiement(DemandePaiement("p", 500)))
            banc.erreur_lecture = True
            self.attendre(lambda: not pont.en_cours)
        self.assertEqual(r.paiements, [])
        self.assertEqual(self.lignes_journal(), [])
        self.assertTrue(r.erreurs[0].fatal)
        self.assertEqual(banc.fermetures, ["uart", "rng", "fabrique"])

    def test_modules_t03_t04_t13_gardent_leurs_files_et_soldes_communs(self):
        lectures, paiements, threads = [], [], []

        def t03(acces):
            return Mock(actualiser=lambda: lectures.extend(acces.lire_identifications()))

        def t04(acces):
            acces.demander_paiement(DemandePaiement("p", 500))
            return Mock(actualiser=lambda: paiements.extend(acces.lire_resultats_paiement()))

        def t13(acces):
            def actualiser():
                if not threads:
                    threads.append(get_ident())
                    acces.ajouter_credit("c", JASON, 500)
            return Mock(actualiser=actualiser)

        with patch.object(integration_t03, "creer_module_t03", t03), \
             patch.object(integration_t04, "creer_module_t04", t04), \
             patch.object(integration_t13, "creer_module_t13", t13):
            pont, r = self.ouvrir()
            self.attendre(lambda: bool(threads))
            self.reponse(r, pont.simuler_badge(JASON))
            self.attendre(lambda: len(paiements) == 1)
            self.reponse(r, pont.simuler_badge(LUCIA))
            self.attendre(lambda: len(lectures) == 1)
            pont.arreter()
            self.attendre(lambda: not pont.en_cours)
        self.assertNotEqual(threads[0], get_ident())
        self.assertEqual(lectures[0].id_uart, LUCIA)
        self.assertEqual(paiements, r.paiements)
        self.assertEqual(self.solde(), 2000)

    def test_ui_reste_active_pendant_ecriture_et_arret_attend_confirmation(self):
        pont, r = self.ouvrir()
        entre, liberer = Event(), Event()
        ecrire = stockage._ecrire_csv_atomique

        def ecrire_lentement(chemin, champs, lignes):
            if chemin.name == "operations.csv":
                entre.set()
                if not liberer.wait(timeout=5):
                    raise OSError("test : liberation manquante")
            return ecrire(chemin, champs, lignes)

        battements = []
        timer = QTimer()
        timer.timeout.connect(lambda: battements.append(True))
        timer.start(5)
        try:
            with patch.object(stockage, "_ecrire_csv_atomique", ecrire_lentement):
                reference = pont.ajouter_credit("c", JASON, 500)
                self.attendre(entre.is_set)
                nombre = len(battements)
                pont.arreter()
                self.attendre(lambda: len(battements) >= nombre + 3)
                self.assertTrue(pont.en_cours)
                with self.assertRaises(RuntimeError):
                    pont.ajouter_credit("c2", JASON, 500)
                liberer.set()
                self.attendre(lambda: not pont.en_cours)
        finally:
            liberer.set()
            timer.stop()
        self.assertTrue(r.reponses[reference][1].succes)
        self.assertEqual(self.solde(), 2500)
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_arret_immediat_et_redemarrage_du_meme_pont(self):
        pont, r = self.nouveau_pont(simulation=True)
        pont.demarrer()
        pont.arreter()
        self.attendre(lambda: not pont.en_cours)
        with self.assertRaises(RuntimeError):
            pont.lister_soldes()
        r.comptes = None
        pont.demarrer()
        self.attendre(lambda: r.comptes is not None)
        self.assertEqual(self.reponse(r, pont.lister_soldes()), {JASON: 2000, LUCIA: 2000})
        self.assertEqual(r.erreurs, [])

    def test_boutons_graphique_paiement_credit_repetitions_et_fermeture(self):
        pont, r = self.nouveau_pont(simulation=True)
        fenetre = FenetreDemoT02(pont)
        self.fenetres.append(fenetre)
        fenetre.show()
        fenetre.demarrer()
        self.attendre(lambda: fenetre.preparer.isEnabled())
        fenetre.preparer.click()
        self.attendre(lambda: fenetre.annuler.isEnabled())
        fenetre.badges[0].click()
        self.attendre(lambda: fenetre.table.item(0, 2).text() == "15,00 $")
        fenetre.rejouer_paiement.click()
        self.attendre(lambda: len(r.paiements) == 2)
        self.assertTrue(r.paiements[-1].deja_traitee)
        fenetre.crediter.click()
        self.attendre(lambda: fenetre.table.item(0, 2).text() == "20,00 $")
        fenetre.rejouer_credit.click()
        self.attendre(lambda: not fenetre._envoi_credit)
        self.assertEqual(len(self.lignes_journal()), 2)
        fenetre.badges[2].click()
        self.attendre(lambda: "Carte refusée" in fenetre.message.text())
        fenetre.close()
        self.attendre(lambda: not pont.en_cours and not fenetre.isVisible())
        self.assertEqual(r.erreurs, [])

    def test_fermeture_fenetre_pendant_attente_sans_debit(self):
        pont, r = self.nouveau_pont(simulation=True)
        fenetre = FenetreDemoT02(pont)
        self.fenetres.append(fenetre)
        fenetre.show()
        fenetre.demarrer()
        self.attendre(lambda: fenetre.preparer.isEnabled())
        fenetre.preparer.click()
        self.attendre(lambda: fenetre.annuler.isEnabled())
        # Des messages de lecteur peuvent encore etre en transit pendant closeEvent.
        pont.simuler_badge(INCONNU)
        fenetre.close()
        self.attendre(lambda: not pont.en_cours and not fenetre.isVisible())
        self.assertEqual(self.solde(), 2000)
        self.assertTrue(all(l["statut"] == "COMPTE_INCONNU" for l in self.lignes_journal()))

    def test_fenetre_conserve_attente_creee_par_t04_avant_signal_pret(self):
        def creer_t04(paiements):
            paiements.demander_paiement(DemandePaiement("initial", 500))
            return Mock(actualiser=paiements.lire_resultats_paiement)

        def creer_t13(comptes):
            comptes.ajouter_credit("credit-initial", JASON, 500)
            return None

        with patch.object(integration_t04, "creer_module_t04", creer_t04), \
             patch.object(integration_t13, "creer_module_t13", creer_t13):
            pont, r = self.nouveau_pont(simulation=True)
            fenetre = FenetreDemoT02(pont)
            self.fenetres.append(fenetre)
            fenetre.show()
            fenetre.demarrer()
            self.attendre(lambda: fenetre._prete)
            self.assertEqual(fenetre._attente.id_transaction, "initial")
            self.assertEqual(fenetre.table.item(0, 2).text(), "25,00 $")
            self.assertTrue(fenetre.annuler.isEnabled())
            self.assertFalse(fenetre.preparer.isEnabled())
            fenetre.annuler.click()
            self.attendre(lambda: fenetre.preparer.isEnabled())
            self.assertEqual(len(self.lignes_journal()), 1)
            fenetre.close()
            self.attendre(lambda: not pont.en_cours)

    def test_fenetre_reprend_meme_paiement_apres_erreur_csv(self):
        pont, r = self.nouveau_pont(simulation=True)
        fenetre = FenetreDemoT02(pont)
        self.fenetres.append(fenetre)
        fenetre.show()
        fenetre.demarrer()
        self.attendre(lambda: fenetre.preparer.isEnabled())
        fenetre.preparer.click()
        self.attendre(lambda: fenetre.annuler.isEnabled())
        with patch.object(stockage, "_ecrire_comptes", side_effect=OSError("interruption")):
            fenetre.badges[0].click()
            self.attendre(lambda: not pont.en_cours)
        self.assertTrue(fenetre._reprise_paiement)
        self.assertFalse(fenetre.preparer.isEnabled())
        fenetre.relancer.click()
        self.attendre(lambda: fenetre.rejouer_paiement.isEnabled())
        self.assertFalse(fenetre.preparer.isEnabled())
        fenetre.rejouer_paiement.click()
        self.attendre(lambda: bool(r.paiements))
        self.assertTrue(r.paiements[-1].deja_traitee)
        self.attendre(lambda: fenetre.table.item(0, 2).text() == "15,00 $")
        self.assertEqual(len(self.lignes_journal()), 1)


if __name__ == "__main__":
    unittest.main()
