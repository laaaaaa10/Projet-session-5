"""Essais déterministes T12 ; aucun matériel, broker ou GPIO."""
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

PROG = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROG / 'rpi'), str(PROG)]

from exemples.banc_retrait import BancRetrait, BusRetraitSimule, TABLE_IR_SIMULEE, CARTE
from exemples.service_retrait_simule import ServiceRetraitSimule
from modules.arbitrage_mecanique import ArbitreMecanique
from modules.demande_retrait import GestionDemandeRetrait, EtapeDemandeRetrait as D
from modules.depot import EtapeDepot
from modules.retrait import GestionRetrait, EtapeRetrait as E
from modules.service_t13 import GestionServiceT13
from modules.stationnement import EtatPlace, Presence
from commun.t13.protocole import nouvelle_commande


class Banc(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='esa-t12-mecanique-')
        self.addCleanup(self.temp.cleanup)
        self.racine = Path(self.temp.name)
        self.b = BancRetrait(self.racine)
        self.addCleanup(self.b.fermer)
        self.b.t12.autoriser_nouvelles(True)

    def demarrer(self):
        self.b.payer()
        self.assertTrue(self.b.t12.autoriser_apres_paiement('retrait-1'), self.b.t12.derniere_erreur)

    def acces(self):
        self.demarrer()
        self.b.jusqu_a(E.ACCES)

    def verifier_defaut(self):
        b = self.b
        self.assertEqual(b.t12.etape, E.DEFAUT, b.t12.derniere_erreur)
        self.assertTrue(b.t12.arbitre.bloque)
        self.assertEqual(b.can.envoyees[-1], (0x004, bytes([1, 6, 0])))
        self.assertEqual(b.t04.nombre_clotures, 0)
        avant = list(b.can.envoyees)
        b.tour()
        self.assertEqual(b.can.envoyees, avant)
        self.assertFalse(b.t12.autoriser_apres_paiement('retrait-1'))


class TestsRetrait(Banc):
    def test_paiement_ne_demarre_aucun_moteur(self):
        self.assertFalse(self.b.t12.autoriser_apres_paiement('retrait-1'))
        self.b.payer()
        self.assertEqual(self.b.can.envoyees, [])

    def test_nominal_sortie_niveau_1_retour_0_et_cloture_unique(self):
        b = self.b
        self.demarrer()
        b.jusqu_a(E.ATTENTE_MANUEL)
        self.assertTrue(b.t12.place_liberee)
        self.assertTrue(b.t12.arrivee_sortie)
        self.assertFalse(b.t12.depart_confirme)
        self.assertEqual(b.modele.etat(10), EtatPlace.OCCUPEE)
        self.assertEqual(b.modele.presence(10), Presence.ABSENT)
        self.assertEqual(b.t04.nombre_clotures, 0)
        actions = [(i, d[1], d[2]) for i, d in b.can.envoyees]
        self.assertEqual(actions, [
            (0x120, 3, 0), (0x100, 2, 0), (0x110, 2, 255),
            (0x100, 1, 2), (0x110, 1, 3), (0x120, 1, 0),
            (0x100, 3, 0), (0x120, 2, 0), (0x110, 1, 0),
            (0x100, 1, 1), (0x120, 1, 0), (0x100, 4, 0),
            (0x120, 2, 0), (0x100, 1, 0)])
        b.can.ir_sortie(False)
        b.tour()
        self.assertEqual(b.t12.etape, E.TERMINE)
        self.assertEqual(b.t04.nombre_clotures, 1)
        self.assertEqual(b.modele.etat(10), EtatPlace.LIBRE)
        self.assertEqual(b.demande.etape, D.CLOTURE)
        self.assertIsNone(b.t12.arbitre.proprietaire)
        avant = list(b.can.envoyees)
        for _ in range(3):
            self.assertTrue(b.t12.autoriser_apres_paiement('retrait-1'))
            b.can.ir_sortie(False)
            b.tour()
        self.assertEqual(b.can.envoyees, avant)
        self.assertEqual(b.t04.nombre_clotures, 1)
        self.assertEqual(b.comptes.consulter_compte(CARTE).solde_centimes, 800)

    def test_deux_transactions_successives_sans_rejouer_la_premiere(self):
        self.demarrer()
        b = self.b
        b.jusqu_a(E.ATTENTE_MANUEL)
        b.can.ir_sortie(False)
        b.tour()
        b.t04.ajouter_transaction(654321, 3, depose_a=0)
        b.modele.changer_etat(3, EtatPlace.OCCUPEE)
        b.can.ir_place(3, True)
        b.can.synchroniser_ir()
        b.tour()
        self.assertTrue(b.t12.demander_retrait(654321, id_demande='retrait-2'))
        self.assertTrue(b.t12.confirmer_retrait_et_figer_montant('retrait-2'))
        self.assertTrue(b.t04.avant_presentation())
        from modules.lecteur_nfc_rfid import EvenementRFID
        b.borne.traiter_evenement(EvenementRFID('ACCEPTE', 'banc', CARTE))
        b.t04.apres_presentation()
        b.tour()
        self.assertTrue(b.t12.autoriser_apres_paiement('retrait-2'))
        avant = list(b.can.envoyees)
        self.assertTrue(b.t12.autoriser_apres_paiement('retrait-1'))
        self.assertEqual(b.t12.id_demande, 'retrait-2')
        self.assertEqual(b.can.envoyees, avant)
        b.jusqu_a(E.ATTENTE_MANUEL)
        b.can.ir_sortie(False)
        b.tour()
        self.assertEqual(b.t04.nombre_clotures, 2)
        sequences = [d[0] for i, d in b.can.envoyees if i in (0x100, 0x110, 0x120)]
        self.assertEqual(len(sequences), len(set(sequences)))

    def test_acceptation_seule_ne_fait_pas_avancer(self):
        self.acces()
        b = self.b
        avant = list(b.can.envoyees)
        b.can.accepter()
        b.tour()
        self.assertEqual(b.can.envoyees, avant)
        b.can.terminer()
        b.tour()
        self.assertEqual(len(b.can.envoyees), len(avant) + 1)

    def test_fin_sans_acceptation_arrete(self):
        self.acces()
        c = self.b.can.attentes[0]
        self.b.can.reponse(c, 2, position=2)
        self.b.tour()
        self.verifier_defaut()

    def test_mauvaise_sequence_et_mauvais_moteur_ignores(self):
        self.acces()
        b = self.b
        c = b.can.attentes[0]
        avant = list(b.can.envoyees)
        b.can.emettre(0x200, [c[1][0] - 1, 2, 2, 0, 2])
        b.can.emettre(0x210, [c[1][0], 2, 0, 0])
        b.tour()
        self.assertEqual(b.can.envoyees, avant)
        self.assertEqual(b.t12.etape, E.ACCES)

    def test_acceptation_tardive_arrete_meme_avant_tick(self):
        self.acces()
        self.b.horloge.temps += .501
        self.b.can.accepter()
        self.b.tour(0)
        self.verifier_defaut()

    def test_absence_acceptation_arrete(self):
        self.acces()
        self.b.tour(.501)
        self.verifier_defaut()

    def test_acceptations_repetees_ne_prolongent_pas_la_fin(self):
        self.acces()
        b = self.b
        b.can.accepter()
        b.tour(.1)
        b.tour(29.7)
        b.can.reponse(b.can.courante, 1)
        b.tour(.3)
        self.verifier_defaut()
        self.assertIn('Fin de mouvement', b.t12.derniere_erreur)

    def test_position_finale_incorrecte_arrete(self):
        self.acces()
        b = self.b
        b.can.accepter()
        b.tour()
        b.can.reponse(b.can.courante, 2, position=1)
        b.tour()
        self.verifier_defaut()

    def test_reference_verticale_seulement_estimee_refusee_pour_changement_niveau(self):
        self.acces()
        b = self.b
        b.can.accepter()
        b.tour()
        b.can.reponse(b.can.courante, 2, position=2, reference=1)
        b.tour()
        self.verifier_defaut()

    def test_reference_initiale_inconnue_arrete_avant_mouvement(self):
        self.demarrer()
        b = self.b
        b.mouvement()  # bras lu
        b.can.reponse(b.can.attentes[0], 2, position=255, reference=0)
        b.tour()
        self.verifier_defaut()
        self.assertEqual(len([1 for i, d in b.can.envoyees if i in (0x100, 0x110, 0x120)]), 2)

    def test_defaut_spontane_et_non_correle_arrete(self):
        self.acces()
        self.b.can.emettre(0x220, [255, 4, 0, 7])
        self.b.tour()
        self.verifier_defaut()

    def test_position_spontanee_inconnue_arrete(self):
        self.acces()
        self.b.can.emettre(0x210, [255, 2, 255, 0])
        self.b.tour()
        self.verifier_defaut()

    def test_defaut_critique_can_arrete(self):
        self.acces()
        self.b.can.emettre(0x011, [4, 1, 2, 0])
        self.b.tour()
        self.verifier_defaut()

    def test_arret_prioritaire_et_fin_retardee_ne_reprennent_pas(self):
        self.acces()
        b = self.b
        c = b.can.attentes[0]
        b.can.emettre(0x001, [2, 1, 0])
        b.tour()
        self.assertEqual(b.t12.etape, E.INTERROMPU)
        avant = list(b.can.envoyees)
        b.can.reponse(c, 2, position=2)
        b.tour()
        self.assertEqual(b.can.envoyees, avant)
        self.assertEqual(b.t12.etape, E.INTERROMPU)

    def test_perte_heartbeat_arrete(self):
        self.acces()
        b = self.b
        b.can.accepter()
        b.tour()
        b.tour(1.6, surveillance=False)
        self.verifier_defaut()

    def test_heartbeat_revenu_apres_coupure_ne_relance_pas(self):
        self.acces()
        b = self.b
        b.can.accepter()
        b.tour()
        b.horloge.temps += 1.6
        b.can.surveillance()
        b.t12.mettre_a_jour()
        self.verifier_defaut()
        self.assertIn('coupure', b.t12.derniere_erreur)

    def test_heartbeat_repete_ne_prouve_pas_partenaire_vivant(self):
        self.acces()
        b = self.b
        b.can.accepter()
        b.tour()
        compteur = b.can.compteur_hb
        b.horloge.temps += 1.6
        b.can.emettre(0x041, [compteur, 1])
        b.can.emettre(0x042, [compteur, 1])
        b.tour(0, surveillance=False)
        self.verifier_defaut()

    def test_barriere_ouverte_en_sequence_arrete(self):
        self.acces()
        self.b.securite.valeurs = replace(self.b.securite.valeurs, barriere_fermee=False)
        self.b.tour()
        self.verifier_defaut()

    def test_securite_inconnue_ou_sortie_occupee_interdisent_demarrage(self):
        b = self.b
        b.payer()
        for champ in ('barriere_fermee', 'defauts_leves', 'parcours_valide', 'reference_verticale', 'reference_angulaire', 'bras_retracte_sur'):
            ancien = b.securite.valeurs
            b.securite.valeurs = replace(ancien, **{champ: False})
            self.assertFalse(b.t12.autoriser_apres_paiement('retrait-1'), champ)
            b.securite.valeurs = ancien
        b.can.ir_sortie(True)
        b.tour()
        self.assertFalse(b.t12.autoriser_apres_paiement('retrait-1'))
        self.assertEqual(b.can.envoyees, [])

    def test_ir_place_non_fiable_avant_demarrage_invalide_ancienne_presence(self):
        b = self.b
        b.payer()
        b.can.emettre(0x301, [0, 2, 0, 0])
        b.tour()
        self.assertFalse(b.t12.autoriser_apres_paiement('retrait-1'))
        self.assertEqual(b.can.envoyees, [])

    def test_place_absente_attendue_avant_transport(self):
        self.b.can.ir_place_actif = False
        self.demarrer()
        self.b.jusqu_a(E.ATTENTE_PLACE)
        avant = list(self.b.can.envoyees)
        self.b.tour(1)
        self.assertEqual(self.b.can.envoyees, avant)
        self.b.tour(4.1)
        self.verifier_defaut()
        self.assertIn('Absence IR', self.b.t12.derniere_erreur)
        self.assertEqual(self.b.modele.etat(10), EtatPlace.OCCUPEE)

    def test_absence_place_avant_prise_est_anomalie(self):
        self.acces()
        self.b.can.ir_place(10, False)
        self.b.tour()
        self.verifier_defaut()

    def test_ir_sortie_absent_sans_presence_ne_cloture_pas(self):
        self.b.can.ir_sortie_actif = False
        self.demarrer()
        b = self.b
        b.jusqu_a(E.ATTENTE_SORTIE)
        b.can.ir_sortie(False)
        b.tour()
        self.assertFalse(b.t12.depart_confirme)
        self.assertEqual(b.t04.nombre_clotures, 0)
        b.tour(5.1)
        self.verifier_defaut()
        self.assertIn('Présence IR', b.t12.derniere_erreur)

    def test_retrait_manuel_peut_attendre_sans_nouveau_mouvement(self):
        self.demarrer()
        b = self.b
        b.jusqu_a(E.ATTENTE_MANUEL)
        avant = list(b.can.envoyees)
        b.tour(120)
        self.assertEqual(b.t12.etape, E.ATTENTE_MANUEL)
        self.assertEqual(b.can.envoyees, avant)
        self.assertEqual(b.t04.nombre_clotures, 0)

    def test_resynchronisation_absente_ne_fabrique_pas_depart(self):
        self.demarrer()
        b = self.b
        b.jusqu_a(E.ATTENTE_MANUEL)
        b.can.emettre(0x311, [0, b.can.compteur_sortie + 1, 1])
        b.tour()
        self.verifier_defaut()
        self.assertFalse(b.t12.depart_confirme)

    def test_ancien_compteur_absence_ignore(self):
        self.demarrer()
        b = self.b
        b.jusqu_a(E.ATTENTE_MANUEL)
        b.can.emettre(0x310, [0, 0, (b.can.compteur_sortie - 1) % 256])
        b.tour()
        self.assertEqual(b.t12.etape, E.ATTENTE_MANUEL)
        self.assertFalse(b.t12.depart_confirme)

    def test_ir_invalide_arrete_sans_fausse_absence(self):
        self.demarrer()
        b = self.b
        b.jusqu_a(E.ATTENTE_MANUEL)
        b.can.emettre(0x311, [0, b.can.compteur_sortie, 0])
        b.tour()
        self.verifier_defaut()
        self.assertIsNone(b.t12.sortie)

    def test_cadre_moteur_malforme_arrete(self):
        self.acces()
        self.b.can.emettre(0x200, [1, 2])
        self.b.tour()
        self.verifier_defaut()

    def test_file_can_saturee_arrete(self):
        self.acces()
        for _ in range(257):
            self.b.can.emettre(0x041, [1, 1])
        self.b.tour()
        self.verifier_defaut()

    def test_callback_can_autre_thread_ne_touche_pas_sqlite_ni_moteur(self):
        self.demarrer()
        b = self.b
        avant = list(b.can.envoyees)
        c = b.can.attentes[0]
        fil = threading.Thread(target=lambda: b.can.reponse(c, 2))
        fil.start()
        fil.join(timeout=1)
        self.assertFalse(fil.is_alive())
        self.assertEqual(b.can.envoyees, avant)
        b.tour()
        self.assertEqual(len(b.can.envoyees), len(avant) + 1)

    def test_echec_envoi_apres_effet_arrete_sans_retransmission(self):
        b = self.b
        b.payer()
        envoyer = b.can.envoyer
        def perdu(i, d):
            envoyer(i, d)
            if i != 0x004:
                raise OSError('envoi incertain')
        with patch.object(b.can, 'envoyer', side_effect=perdu):
            self.assertFalse(b.t12.autoriser_apres_paiement('retrait-1'))
        self.verifier_defaut()
        self.assertEqual(len(b.can.envoyees), 2)  # une lecture, puis arrêt

    def test_journal_indisponible_avant_emission_interdit_mouvement(self):
        b = self.b
        b.payer()
        b.t12.db.execute('DROP TABLE retraits')
        self.assertFalse(b.t12.autoriser_apres_paiement('retrait-1'))
        self.assertEqual(b.can.envoyees, [(0x004, bytes([1, 6, 0]))])

    def test_erreur_financiere_pendant_mouvement_provoque_arret(self):
        self.acces()
        with patch.object(self.b.demande, 'mettre_a_jour', side_effect=OSError('journal absent')):
            self.b.tour()
        self.verifier_defaut()

    def test_cloture_reponse_perdue_reconciliation_sans_rejeu(self):
        self.demarrer()
        b = self.b
        b.jusqu_a(E.ATTENTE_MANUEL)
        cloturer = b.t04.cloturer_sortie
        def perdu(*args):
            cloturer(*args)
            raise OSError('réponse perdue')
        with patch.object(b.t04, 'cloturer_sortie', side_effect=perdu) as appel:
            b.can.ir_sortie(False)
            b.tour()
            self.assertEqual(b.t12.etape, E.CLOTURE_INCERTAINE)
            b.tour()
            self.assertEqual(appel.call_count, 1)
        avant = list(b.can.envoyees)
        self.assertTrue(b.t12.reconcilier_cloture())
        self.assertEqual(b.t12.etape, E.TERMINE)
        self.assertEqual(b.t04.nombre_clotures, 1)
        self.assertEqual(b.can.envoyees, avant)

    def test_cloture_inconnue_conserve_verrou_et_place(self):
        self.demarrer()
        b = self.b
        b.jusqu_a(E.ATTENTE_MANUEL)
        with patch.object(b.t04, 'cloturer_sortie', return_value=None):
            b.can.ir_sortie(False)
            b.tour()
        self.assertEqual(b.t12.etape, E.CLOTURE_INCERTAINE)
        self.assertEqual(b.modele.etat(10), EtatPlace.OCCUPEE)
        self.assertFalse(b.t12.reconcilier_cloture())
        self.assertIs(b.t12.arbitre.proprietaire, b.t12)

    def test_redemarrage_ne_relance_ni_mouvement_ni_cloture(self):
        self.acces()
        b = self.b
        b.t12.db.close()  # crash : pas de fermeture ordonnée
        b.demande.fermer()
        b.demande = GestionDemandeRetrait(b.t04, self.racine / 'paiement.sqlite3')
        nouveau_can = BusRetraitSimule(b.horloge)
        b.t12 = GestionRetrait(nouveau_can, b.modele, b.t04, demande=b.demande, securite=b.securite,
            journal=self.racine / 'mecanique.sqlite3', table_ir=TABLE_IR_SIMULEE,
            ordre_sortie='rotation_elevation', horloge=b.horloge)
        b.t12.autoriser_nouvelles(True)
        b.t12.mettre_a_jour()
        self.assertEqual(b.t12.etape, E.INTERROMPU)
        self.assertTrue(b.t12.arbitre.bloque)
        self.assertFalse(b.t12.autoriser_apres_paiement('retrait-1'))
        self.assertEqual(nouveau_can.envoyees, [])
        self.assertEqual(b.t04.nombre_clotures, 0)

    def test_arret_apres_fin_ne_modifie_pas_ancienne_transaction(self):
        self.demarrer()
        b = self.b
        b.jusqu_a(E.ATTENTE_MANUEL)
        b.can.ir_sortie(False)
        b.tour()
        b.t12.arreter()
        etape = b.t12.db.execute('SELECT etape FROM retraits WHERE id=?', ('retrait-1',)).fetchone()[0]
        self.assertEqual(etape, E.TERMINE.value)
        self.assertEqual(b.demande.etape, D.CLOTURE)


class TestsArbitrage(Banc):
    def reserver_depot(self):
        self.b.modele.changer_etat(3, EtatPlace.RESERVEE)
        self.b.modele.changer_presence(3, Presence.ABSENT)

    def test_t12_bloque_t11_jusqu_au_depart(self):
        self.reserver_depot()
        self.demarrer()
        b = self.b
        self.assertFalse(b.t11.demarrer(654321, 1, 3))
        b.jusqu_a(E.ATTENTE_MANUEL)
        self.assertFalse(b.t11.demarrer(654321, 1, 3))
        b.can.ir_sortie(False)
        b.tour()
        dernier_seq = b.can.envoyees[-1][1][0]
        self.assertTrue(b.t11.demarrer(654321, 1, 3))
        self.assertGreater(b.can.envoyees[-1][1][0], dernier_seq)

    def test_t11_bloque_t12_et_libere_seulement_en_fin(self):
        self.reserver_depot()
        b = self.b
        b.payer()
        self.assertTrue(b.t11.demarrer(654321, 1, 3))
        self.assertFalse(b.t12.autoriser_apres_paiement('retrait-1'))
        for _ in range(30):
            if b.t11.etape == EtapeDepot.TERMINE:
                break
            b.mouvement()
        self.assertEqual(b.t11.etape, EtapeDepot.TERMINE)
        b.can.synchroniser_ir()
        b.tour()
        self.assertTrue(b.t12.autoriser_apres_paiement('retrait-1'), b.t12.derniere_erreur)

    def test_defaut_t11_garde_arbitre_verrouille(self):
        self.reserver_depot()
        b = self.b
        b.payer()
        b.t11.demarrer(654321, 1, 3)
        b.can.reponse(b.can.attentes[0], 0, code=7)
        b.tour()
        self.assertEqual(b.t11.etape, EtapeDepot.DEFAUT)
        self.assertFalse(b.t12.autoriser_apres_paiement('retrait-1'))

    def test_acquisition_concurrente_ne_donne_qu_un_proprietaire(self):
        arbitre = ArbitreMecanique()
        depart = threading.Barrier(3)
        sorties = []
        def prendre():
            depart.wait()
            sorties.append(arbitre.prendre(object()))
        fils = [threading.Thread(target=prendre) for _ in range(2)]
        for fil in fils:
            fil.start()
        depart.wait()
        for fil in fils:
            fil.join(timeout=1)
        self.assertEqual(sorted(sorties), [False, True])

    def test_t11_seul_conserve_bouclage_historique_sans_255(self):
        a = ArbitreMecanique()
        valeurs = [a.sequence() for _ in range(300)]
        self.assertNotIn(255, valeurs)
        self.assertEqual(valeurs[254:257], [0, 1, 2])

    def test_pas_de_recyclage_des_sequences(self):
        a = ArbitreMecanique(sequences_sans_reemploi=True)
        self.assertEqual(len(set(a.sequence() for _ in range(254))), 254)
        with self.assertRaises(RuntimeError):
            a.sequence()
        a.acquitter(object())
        with self.assertRaises(RuntimeError):
            a.sequence()


class TestsService(Banc):
    def setUp(self):
        super().setUp()
        self.adaptateur = ServiceRetraitSimule(self.b)
        self.service = GestionServiceT13(self.adaptateur, self.racine / 'service.sqlite3', horloge=self.b.horloge)
        self.addCleanup(self.service.fermer)

    def ordre(self, action):
        return self.service.traiter(nouvelle_commande(action))

    def test_hors_service_differe_attend_depart_reel_du_banc(self):
        b = self.b
        self.assertEqual(self.service.etat, 'HORS_SERVICE')
        self.ordre('REMETTRE_EN_SERVICE')
        self.demarrer()
        self.ordre('METTRE_HORS_SERVICE')
        self.assertEqual(self.service.etat, 'MISE_HORS_SERVICE')
        b.jusqu_a(E.ATTENTE_MANUEL)
        self.service.actualiser()
        self.assertEqual(self.service.etat, 'MISE_HORS_SERVICE')
        b.can.ir_sortie(False)
        b.tour()
        reponses = self.service.actualiser()
        self.assertEqual(reponses[-1]['phase'], 'TERMINEE')
        self.assertEqual(self.service.etat, 'HORS_SERVICE')
        self.assertFalse(b.t12.arbitre.nouvelles_autorisees)

    def test_retrait_deja_confirme_peut_partir_pendant_mise_hors_service(self):
        b = self.b
        self.ordre('REMETTRE_EN_SERVICE')
        b.payer()
        self.ordre('METTRE_HORS_SERVICE')
        self.assertEqual(self.service.etat, 'MISE_HORS_SERVICE')
        self.assertTrue(b.t12.autoriser_apres_paiement('retrait-1'))

    def test_arret_reinitialisation_reste_hors_service_sans_reprise(self):
        b = self.b
        self.ordre('REMETTRE_EN_SERVICE')
        self.acces()
        self.ordre('ARRET_IMMEDIAT')
        self.assertEqual(self.service.etat, 'ARRET_VERROUILLE')
        self.assertEqual(b.t12.etape, E.INTERROMPU)
        avant = list(b.can.envoyees)
        self.adaptateur.intervention_simulee()
        self.assertEqual(self.ordre('REINITIALISER')[-1]['phase'], 'ACCEPTEE')
        b.tour(.6)
        self.service.actualiser()
        self.assertEqual(self.service.etat, 'HORS_SERVICE')
        self.assertEqual(b.t12.etape, E.INTERROMPU)
        self.assertEqual(b.can.envoyees, avant)
        self.assertEqual(self.ordre('REMETTRE_EN_SERVICE')[-1]['code'], 'SYSTEME_NON_PRET')

    def test_demande_non_confirmee_est_annulee_sans_paiement(self):
        self.ordre('REMETTRE_EN_SERVICE')
        self.b.t12.demander_retrait(123456, id_demande='demande')
        self.ordre('METTRE_HORS_SERVICE')
        self.assertEqual(self.b.demande.etape, D.ANNULE)
        self.assertEqual(self.b.t04.gels, 0)
        self.assertEqual(self.b.can.envoyees, [])

    def test_expiration_du_paiement_termine_mise_hors_service_sans_mouvement(self):
        b = self.b
        self.ordre('REMETTRE_EN_SERVICE')
        b.t12.demander_retrait(123456, id_demande='expire')
        b.t12.confirmer_retrait_et_figer_montant('expire')
        self.ordre('METTRE_HORS_SERVICE')
        self.assertEqual(self.service.etat, 'MISE_HORS_SERVICE')
        b.tour(60)
        self.service.actualiser()
        self.assertEqual(b.demande.etape, D.EXPIRE)
        self.assertEqual(self.service.etat, 'HORS_SERVICE')
        self.assertEqual(b.can.envoyees, [])
        self.assertEqual(b.comptes.consulter_compte(CARTE).solde_centimes, 1000)

    def test_arret_pendant_paiement_annule_attente(self):
        b = self.b
        self.ordre('REMETTRE_EN_SERVICE')
        b.t12.demander_retrait(123456, id_demande='interrompu')
        b.t12.confirmer_retrait_et_figer_montant('interrompu')
        self.ordre('ARRET_IMMEDIAT')
        self.assertFalse(b.t04.avant_presentation())
        self.assertEqual(b.demande.etape, D.INTERROMPU)
        self.assertEqual(b.comptes.consulter_compte(CARTE).solde_centimes, 1000)

    def test_t11_ne_peut_partir_hors_service(self):
        self.b.modele.changer_etat(3, EtatPlace.RESERVEE)
        self.assertFalse(self.b.t11.demarrer(654321, 1, 3))

    def test_coupure_mqtt_sequence_continue_et_reponse_finale_retrouvee(self):
        import test_t13_mqtt as mqtt
        from modules.supervision import SupervisionT13
        b = self.b
        pi, pc = mqtt.TransportSimule(), mqtt.TransportSimule()
        pi.pair, pc.pair = pc, pi
        supervision = SupervisionT13(mqtt.AccesComptes(b.comptes), pi,
                                    service=self.service, horloge=b.horloge)
        journal = mqtt.JournalDemandes(self.racine / 'pc.sqlite3', 't12-simulation')
        client = mqtt.ClientSupervision(pc, journal, horloge=b.horloge)
        self.addCleanup(client.fermer)
        def tour():
            client.actualiser()
            supervision.actualiser()
            client.actualiser()
        tour()
        client.demander('REMETTRE_EN_SERVICE')
        tour()
        self.demarrer()
        identifiant = client.demander('METTRE_HORS_SERVICE')
        tour()
        self.assertEqual(self.service.etat, 'MISE_HORS_SERVICE')
        pi.etat = pc.etat = (False, 1, 'coupure simulée')
        for _ in range(40):
            if b.t12.etape == E.ATTENTE_MANUEL:
                break
            b.mouvement()
            tour()
        self.assertEqual(b.t12.etape, E.ATTENTE_MANUEL)
        b.can.ir_sortie(False)
        b.tour()
        tour()
        self.assertEqual(self.service.etat, 'HORS_SERVICE')
        self.assertEqual(b.t04.nombre_clotures, 1)
        avant = list(b.can.envoyees)
        pi.etat = pc.etat = (True, 2, '')
        b.tour(4)
        tour()
        tour()
        resultat = next(l['reponse'] for l in journal.historique()
                        if l['reponse'] and l['reponse']['id_commande'] == identifiant)
        self.assertEqual(resultat['phase'], 'TERMINEE')
        self.assertTrue(resultat['donnees']['deja_traitee'])
        self.assertEqual(b.can.envoyees, avant)
        self.assertEqual(b.comptes.consulter_compte(CARTE).solde_centimes, 800)


if __name__ == '__main__':
    unittest.main()
