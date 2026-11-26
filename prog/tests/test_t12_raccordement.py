"""Vraies Borne/T12/T13 et fenêtre T01 ; partenaires simulés, aucun matériel."""
from dataclasses import replace
from pathlib import Path
from queue import Queue, Empty
import os
import sys
from tempfile import TemporaryDirectory
from threading import get_ident
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PROG = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROG / 'rpi'), str(PROG)]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from application.integration_t12 import RaccordementRetrait, LecteurGardeRetrait, VueRetrait
from application import integration_t04, integration_t12, integration_t13
from commun.t13.protocole import nouvelle_commande
from exemples.banc_retrait import (BancRetrait, BusRetraitSimule, FacturationSortieSimulee,
    HorlogeSimulee, SecuriteSimulee, TABLE_IR_SIMULEE, CARTE)
from exemples.service_retrait_simule import ServiceRetraitSimule
from modules.demande_retrait import GestionDemandeRetrait
from modules.lecteur_nfc_rfid import EvenementRFID
from modules.retrait import creer_gestion_retrait, EtapeRetrait as M
from modules.service_t13 import GestionServiceT13
from modules.stationnement import EtatPlace


class TestsGardeRetrait(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.b = BancRetrait(self.temp.name)
        self.app = RaccordementRetrait(self.b.t12, t04=self.b.t04, etat_service=lambda: 'EN_SERVICE')
        self.addCleanup(self.app.fermer)
        self.b.t12.autoriser_nouvelles(True)

    def confirmer(self):
        self.assertEqual(self.app.demander(123456, 'r').phase, 'DEMANDE')
        self.assertEqual(self.app.confirmer('r').phase, 'ATTENTE_PAIEMENT')

    def presenter(self, lecteur):
        self.b.borne.actualiser(LecteurGardeRetrait(lecteur, self.app), t04=self.b.t04)
        self.app.actualiser()

    def test_controle_chaque_badge_du_meme_lot_et_expire_exactement_a_60_s(self):
        self.confirmer()
        b = self.b
        class Lot:
            def lire(self):
                yield EvenementRFID('ACCEPTE', 'carte inconnue', '0000000099')
                b.horloge.temps += 60
                yield EvenementRFID('ACCEPTE', 'carte valide mais tardive', CARTE)
        self.presenter(Lot())
        self.assertEqual(self.app.vue().phase, 'EXPIRE')
        self.assertEqual(b.comptes.consulter_compte(CARTE).solde_centimes, 1000)
        self.assertEqual(b.can.envoyees, [])
        self.assertEqual(b.borne.lire_resultats_paiement(), [])  # T04 les a consommés

    def test_garde_false_ne_debite_pas_meme_si_t04_oublie_annulation(self):
        self.confirmer()
        lecteur = SimpleNamespace(lire=lambda: [EvenementRFID('ACCEPTE', '', CARTE)])
        with patch.object(self.b.t04, 'avant_presentation', return_value=False):
            self.presenter(lecteur)
        self.assertEqual(self.b.comptes.consulter_compte(CARTE).solde_centimes, 1000)
        self.assertEqual(self.b.can.envoyees, [])

    def test_debit_termine_apres_echeance_interrompt_sans_reprise(self):
        self.confirmer()
        b = self.b
        payer = b.comptes.payer
        def lent(*args):
            resultat = payer(*args)
            b.horloge.temps += 60
            return resultat
        with patch.object(b.comptes, 'payer', lent):
            self.presenter(SimpleNamespace(lire=lambda: [EvenementRFID('ACCEPTE', '', CARTE)]))
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(b.comptes.consulter_compte(CARTE).solde_centimes, 800)
        self.assertFalse(any(i in (0x100, 0x110, 0x120) for i, _ in b.can.envoyees))
        avant = list(b.can.envoyees)
        self.app.actualiser()
        self.assertEqual(b.can.envoyees, avant)

    def test_precontrole_bloque_avant_gel_et_paiement(self):
        self.app.demander(123456, 'r')
        self.b.securite.valeurs = replace(self.b.securite.valeurs, barriere_fermee=False)
        self.assertEqual(self.app.confirmer('r').phase, 'ANNULE')
        self.assertEqual(self.b.t04.gels, 0)
        self.assertEqual(self.b.can.envoyees, [])

    def test_arbitre_t11_occupe_bloque_avant_gel(self):
        self.app.demander(123456, 'r')
        self.assertTrue(self.b.t12.arbitre.prendre(self.b.t11))
        self.assertEqual(self.app.confirmer('r').phase, 'ANNULE')
        self.assertEqual(self.b.t04.gels, 0)

    def test_refus_depart_apres_paiement_ne_retente_pas_au_timer(self):
        self.confirmer()
        self.b.securite.valeurs = replace(self.b.securite.valeurs, barriere_fermee=False)
        self.presenter(SimpleNamespace(lire=lambda: [EvenementRFID('ACCEPTE', '', CARTE)]))
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        avant = list(self.b.can.envoyees)
        self.b.securite.valeurs = replace(self.b.securite.valeurs, barriere_fermee=True)
        for _ in range(3):
            self.app.actualiser()
        self.assertEqual(self.b.can.envoyees, avant)

    def test_paiement_deja_valide_gagne_sur_annulation_concurrente(self):
        self.confirmer()
        lecteur = SimpleNamespace(lire=lambda: [EvenementRFID('ACCEPTE', '', CARTE)])
        self.b.borne.actualiser(LecteurGardeRetrait(lecteur, self.app), t04=self.b.t04)
        self.assertEqual(self.app.annuler('r').phase, 'PAYE_ATTENTE_MECANIQUE')
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'PREPARATION')
        self.assertEqual(self.b.comptes.consulter_compte(CARTE).solde_centimes, 800)

    def test_absence_t04_ou_garde_ne_peut_pas_etre_masquee(self):
        r = integration_t12.creer_module_t12(None, dossier=self.temp.name)
        self.assertEqual(r.demander(123456, 'r').phase, 'REFUSE')
        self.assertIn('T04 non raccordée', r.demander(123456, 'r').message)
        with patch.object(self.b.t04, 'avant_presentation', None):
            with self.assertRaisesRegex(ValueError, 'Garde'):
                RaccordementRetrait(self.b.t12, t04=self.b.t04)


try:
    from PyQt6.QtCore import QElapsedTimer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    from interface.ecran_tactile import EcranTactile
    from interface.src.hardware.services import Services
    QT = True
except ModuleNotFoundError as erreur:
    if erreur.name != 'PyQt6':
        raise
    QT = False


@unittest.skipUnless(QT, 'PyQt6 absent : installer prog/rpi/requirements-qt.txt')
class TestsParcoursQtRetrait(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.horloge = HorlogeSimulee()
        self.can = BusRetraitSimule(self.horloge)
        self.commandes = Queue()
        self.vues, self.erreurs, self.threads = [], [], []
        self.patches = []
        self.services = self.f = None
        self.addCleanup(self.fermer)

    def attendre(self, condition, message='Événement Qt attendu'):
        t = QElapsedTimer(); t.start()
        while not condition() and t.elapsed() < 4000:
            QTest.qWait(5)
        self.assertTrue(condition(), message + ' ; ' + str(self.erreurs))

    def modifier(self, cible, valeur):
        p = patch(cible, valeur)
        p.start(); self.patches.append(p)

    def ouvrir(self, *, partenaires=True, activer=True):
        self.activer = activer
        self.modifier('interface.src.hardware.services.ServiceCAN', lambda **_: self.can)
        self.modifier('application.integration_t13.creer_module_t13', lambda _: None)
        if partenaires:
            self.modifier('application.integration_t04.creer_module_t04', self.fabrique_t04)
            self.modifier('application.integration_t12.creer_module_t12', self.fabrique_t12)
        self.services = Services(simulation=True)
        self.f = EcranTactile(self.services)
        self.pont = self.services.pont_t02
        self.pont.retrait_modifie.connect(self.vues.append)
        self.pont.erreur.connect(self.erreurs.append)
        # Le bus du banc n'ouvre aucun port ; seul le vrai travailleur Qt est démarré.
        self.pont.demarrer()
        self.attendre(lambda: self.f.controleur.lecteur_pret)

    def fabrique_t04(self, borne):
        self.threads.append(get_ident())
        t04 = self.t04 = FacturationSortieSimulee(borne, self.services.modele, horloge=self.horloge)
        t04.ajouter_transaction(123456, 10, depose_a=0)
        # Données synthétiques créées via le service T02 du travailleur, jamais des comptes réels.
        carte = next(iter(borne.comptes.lister_comptes()))
        self.carte = carte
        actualiser = t04.actualiser
        def actualiser_banc():
            self.threads.append(get_ident())
            while True:
                try:
                    action = self.commandes.get_nowait()
                except Empty:
                    break
                action()
            actualiser()
        t04.actualiser = actualiser_banc
        return t04

    def fabrique_t12(self, t04, *, dossier, can, stationnement, depot, t13):
        self.threads.append(get_ident())
        self.assertIs(can, self.services.can)
        self.assertIs(stationnement, self.services.modele)
        self.assertIs(depot, self.services.depot)
        stationnement.changer_etat(10, EtatPlace.OCCUPEE)
        d = GestionDemandeRetrait(t04, Path(dossier) / 'demande.sqlite3')
        securite = SecuriteSimulee(self.horloge)
        g = creer_gestion_retrait(can, stationnement, t04, demande=d, securite=securite,
            journal=Path(dossier) / 'mecanique.sqlite3', table_ir=TABLE_IR_SIMULEE,
            ordre_sortie='rotation_elevation', horloge=self.horloge)
        self.gestion = g
        can.surveillance(); can.synchroniser_ir(); g.mettre_a_jour()
        banc = SimpleNamespace(can=can, t12=g, t11=depot, demande=d, securite=securite, horloge=self.horloge)
        service = self.service = GestionServiceT13(ServiceRetraitSimule(banc),
            Path(dossier) / 'service.sqlite3', horloge=self.horloge)
        if self.activer:
            service.traiter(nouvelle_commande('REMETTRE_EN_SERVICE'))
        class RaccordementBanc(RaccordementRetrait):
            def actualiser(self):
                service.actualiser()
                super().actualiser()
            def fermer(self):
                try:
                    super().fermer()
                finally:
                    service.fermer()
        return RaccordementBanc(g, t04=t04, etat_service=lambda: service.etat)

    def fermer(self):
        if self.services is not None:
            self.services.pont_t02.arreter()
            self.attendre(lambda: not self.services.pont_t02.en_cours, 'Travailleur encore actif')
            self.f.controleur.minuterie_suivi.stop()
            self.f.close(); self.qt.processEvents()
            if self.services._donnees_temp:
                self.services._donnees_temp.cleanup()
        for p in reversed(self.patches):
            p.stop()

    def saisir(self):
        self.f.controleur.commencer_retrait()
        self.f.controleur.numero_saisi(123456)
        self.attendre(lambda: bool(self.vues))
        return self.f.controleur.session.id_retrait

    def confirmer(self):
        identifiant = self.saisir()
        self.assertEqual(self.vues[-1].phase, 'DEMANDE')
        self.assertEqual(self.t04.gels, 0)
        self.f.ecran_recuperation.bouton_confirmer.click()
        self.attendre(lambda: self.vues[-1].phase == 'ATTENTE_PAIEMENT')
        return identifiant

    def payer(self):
        self.pont.simuler_badge(self.carte)
        self.attendre(lambda: self.vues[-1].phase == 'PREPARATION')

    def finir_mecanique(self):
        for _ in range(35):
            self.can.surveillance(); self.can.accepter(); self.can.terminer()
            QTest.qWait(5)
            if self.vues[-1].phase == 'ATTENTE_RETRAIT_MANUEL':
                return
        self.fail(str(self.vues[-1]))

    def test_fenetre_principale_refuse_sans_t04_avant_paiement(self):
        self.ouvrir(partenaires=False)
        self.saisir()
        self.assertEqual(self.vues[-1].phase, 'REFUSE')
        self.assertIn('T04 non raccordée', self.vues[-1].message)
        self.assertEqual(self.can.envoyees, [])

    def test_parcours_complet_confirmations_repetitions_et_threads(self):
        self.ouvrir()
        identifiant = self.confirmer()
        self.pont.confirmer_retrait(identifiant)
        self.payer()
        self.finir_mecanique()
        self.assertEqual(self.t04.gels, 1)
        self.assertEqual(self.t04.nombre_clotures, 0)
        self.assertIn('Retirez votre véhicule', self.f.ecran_recuperation.texte.text())
        self.assertEqual(self.services.modele.etat(10), EtatPlace.OCCUPEE)
        self.can.ir_sortie(False)
        self.attendre(lambda: self.vues[-1].phase == 'TERMINE')
        self.assertEqual(self.t04.nombre_clotures, 1)
        self.assertEqual(self.services.modele.etat(10), EtatPlace.LIBRE)
        self.assertEqual(self.f.ecran_courant(), 'message')
        avant = list(self.can.envoyees)
        self.pont.demander_retrait(123456, identifiant)
        self.pont.confirmer_retrait(identifiant)
        QTest.qWait(30)
        self.assertEqual(self.can.envoyees, avant)
        self.assertEqual(self.t04.nombre_clotures, 1)
        self.assertTrue(self.threads)
        self.assertTrue(all(t != get_ident() for t in self.threads))
        self.assertEqual(self.erreurs, [])

    def test_recu_t02_seul_et_ancien_crochet_ne_valident_pas_retrait(self):
        from modeles.comptes import StatutOperation
        self.ouvrir(); self.confirmer()
        s = self.f.controleur.session
        self.f.controleur.resultat_paiement(SimpleNamespace(
            id_transaction=s.id_paiement, statut=StatutOperation.PAIE))
        self.f.controleur.etat_operation('termine', 'ancienne réponse sans ID')
        self.assertFalse(s.en_cours)
        self.assertEqual(self.f.ecran_courant(), 'recuperation')
        self.assertEqual(self.can.envoyees, [])

    def test_refus_carte_reste_sur_paiement_puis_autre_carte_paie_tout(self):
        self.ouvrir(); self.confirmer()
        premier = self.f.controleur.session.id_paiement
        self.pont.simuler_badge('0000000099')
        self.attendre(lambda: self.f.controleur.session.id_paiement != premier)
        self.assertEqual(self.f.ecran_courant(), 'recuperation')
        self.assertFalse(self.f.controleur.session.en_cours)
        self.assertEqual(self.t04.gels, 1)
        self.payer()
        self.assertEqual(self.t04.gels, 1)

    def test_erreur_confirmation_arrete_travailleur_et_ne_laisse_pas_ui_en_attente(self):
        self.ouvrir(); self.saisir()
        with patch.object(self.gestion, 'confirmer_retrait_et_figer_montant',
                          side_effect=OSError('journal indisponible')):
            self.f.ecran_recuperation.bouton_confirmer.click()
            self.attendre(lambda: not self.pont.en_cours)
        self.assertTrue(self.erreurs[0].fatal)
        self.assertEqual(self.erreurs[0].action, 'confirmer_retrait')
        self.assertIn('Contactez le personnel', self.f.ecran_recuperation.texte.text())
        self.assertFalse(any(i in (0x100, 0x110, 0x120) for i, _ in self.can.envoyees))

    def test_commande_pendant_fermeture_ne_leve_pas_exception_gui(self):
        self.ouvrir(); self.confirmer()
        self.pont.arreter()
        self.f.controleur.annuler()
        self.assertIn('Service indisponible', self.f.ecran_recuperation.texte.text())
        self.attendre(lambda: not self.pont.en_cours)

    def test_mise_hors_service_differee_attend_depart_manuel(self):
        self.ouvrir()
        self.confirmer()
        self.commandes.put(lambda: self.service.traiter(nouvelle_commande('METTRE_HORS_SERVICE')))
        self.attendre(lambda: self.service.etat == 'MISE_HORS_SERVICE')
        self.payer(); self.finir_mecanique()
        self.assertEqual(self.service.etat, 'MISE_HORS_SERVICE')
        self.can.ir_sortie(False)
        self.attendre(lambda: self.service.etat == 'HORS_SERVICE')
        self.assertEqual(self.t04.nombre_clotures, 1)

    def test_arret_immediat_n_enchaine_pas_apres_reponses_tardives(self):
        self.ouvrir(); self.confirmer(); self.payer()
        self.commandes.put(lambda: self.service.traiter(nouvelle_commande('ARRET_IMMEDIAT')))
        self.attendre(lambda: self.vues[-1].phase == 'INTERROMPU')
        avant = list(self.can.envoyees)
        self.can.surveillance(); self.can.accepter(); self.can.terminer()
        QTest.qWait(30)
        self.assertEqual(self.can.envoyees, avant)
        self.assertEqual(self.t04.nombre_clotures, 0)
        self.assertFalse(self.f.ecran_recuperation.bouton_annuler.isEnabled())

    def test_annulation_attend_confirmation_et_ignore_ancienne_vue(self):
        self.ouvrir(); identifiant = self.confirmer()
        self.f.controleur.annuler()
        self.assertEqual(self.f.controleur.session.id_retrait, identifiant)
        self.attendre(lambda: self.vues[-1].phase == 'ANNULE')
        self.f.controleur.retour_accueil()
        self.f.controleur.commencer_retrait()
        self.f.controleur.retrait_modifie(VueRetrait(identifiant, 123456, 'TERMINE'))
        self.assertEqual(self.f.ecran_courant(), 'saisie_billet')
        self.assertEqual(self.can.envoyees, [])

    def test_expiration_du_paiement_non_prolongee_par_interface(self):
        self.ouvrir(); self.confirmer()
        self.assertFalse(self.f.controleur.minuterie_inactivite.isActive())
        self.horloge.temps += 60
        self.attendre(lambda: self.vues[-1].phase == 'EXPIRE')
        self.assertEqual(self.can.envoyees, [])

    def test_hors_service_refuse_nouvelle_demande(self):
        self.ouvrir(activer=False); self.saisir()
        self.assertEqual(self.vues[-1].phase, 'REFUSE')
        self.assertEqual(self.t04.gels, 0)
        self.assertEqual(self.can.envoyees, [])

    def test_redemarrage_travailleur_ne_cumule_pas_abonnements_ni_reprise(self):
        self.ouvrir(); self.confirmer()
        abonnements = len(self.can._abonnements)
        ancien = self.gestion
        self.pont.arreter()
        self.attendre(lambda: not self.pont.en_cours)
        self.assertFalse(any(cb == ancien.traiter_trame for _, cb in self.can._abonnements))
        self.pont.demarrer()
        self.attendre(lambda: self.pont._accepte_commandes)
        self.assertEqual(len(self.can._abonnements), abonnements)
        self.assertNotEqual(self.service.etat, 'EN_SERVICE')
        self.assertFalse(any(i in (0x100, 0x110, 0x120) for i, _ in self.can.envoyees))
        self.assertEqual(self.erreurs, [])

    def test_fermeture_pendant_paiement_annule_attente_et_ferme_journaux(self):
        self.ouvrir(); self.confirmer()
        self.pont.arreter()
        self.attendre(lambda: not self.pont.en_cours)
        self.assertIsNone(self.t04.paiements._demande)
        self.assertEqual(self.t04.nombre_clotures, 0)
        self.assertFalse(any(i in (0x100, 0x110, 0x120) for i, _ in self.can.envoyees))
        self.assertEqual(self.erreurs, [])


if __name__ == '__main__':
    unittest.main()
