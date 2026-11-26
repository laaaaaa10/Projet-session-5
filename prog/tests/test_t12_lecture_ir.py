"""Lecture T06 avant gel et départ : T04 simulé, aucune commande de mouvement réel."""
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

PROG = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROG / 'rpi'), str(PROG)]

from application.integration_t12 import RaccordementRetrait, LecteurGardeRetrait
from commun.t13.protocole import nouvelle_commande
from exemples.banc_retrait import BancRetrait, CARTE, TABLE_IR_SIMULEE
from exemples.service_retrait_simule import ServiceRetraitSimule
from modules.lecteur_nfc_rfid import EvenementRFID
from modules.retrait import creer_gestion_retrait
from modules.service_t13 import GestionServiceT13

try:
    import can
except ModuleNotFoundError:
    can = None


class TestsLectureIRRetrait(unittest.TestCase):
    def setUp(self):
        self.nouveau_banc()

    def nouveau_banc(self):
        t = TemporaryDirectory(prefix='esa-t12-ir-')
        self.addCleanup(t.cleanup)
        self.b = BancRetrait(t.name)
        self.b.can.repondre_lecture_ir = False
        self.etat_service = 'EN_SERVICE'
        self.app = RaccordementRetrait(self.b.t12, t04=self.b.t04,
                                      etat_service=lambda: self.etat_service)
        self.addCleanup(self.app.fermer)
        self.b.t12.autoriser_nouvelles(True)

    def confirmer(self, identifiant='r'):
        self.assertEqual(self.app.demander(123456, identifiant).phase, 'DEMANDE')
        self.assertEqual(self.app.confirmer(identifiant).phase, 'VERIFICATION_IR')
        self.assertEqual(self.b.t04.gels, 0)

    def ouvrir_paiement(self):
        self.confirmer()
        self.b.can.synchroniser_ir()
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'ATTENTE_PAIEMENT')

    def payer(self):
        lecteur = SimpleNamespace(lire=lambda: [EvenementRFID('ACCEPTE', 'banc', CARTE)])
        self.b.borne.actualiser(LecteurGardeRetrait(lecteur, self.app), t04=self.b.t04)
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'VERIFICATION_IR_APRES_PAIEMENT')

    def aucune_commande_actionneur(self):
        self.assertFalse(any(i in (0x100, 0x110, 0x120) for i, _ in self.b.can.envoyees))

    def avancer(self, secondes):
        self.b.horloge.temps += secondes
        self.b.can.surveillance()
        self.app.actualiser()

    def test_exige_deux_etats_complets_avant_gel_sans_commande_actionneur(self):
        self.confirmer()
        self.assertEqual(self.b.can.envoyees, [(0x302, bytes([0xFF]))])
        self.b.can.emettre(0x301, [0, 2, 0, 1])
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'VERIFICATION_IR')
        self.assertEqual(self.b.t04.gels, 0)
        self.b.can.emettre(0x311, [0, 0, 1])
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'ATTENTE_PAIEMENT')
        self.assertEqual(self.b.t04.gels, 1)
        self.aucune_commande_actionneur()

    def test_cache_perime_et_compteur_identique_sont_rafraichis_par_lecture(self):
        self.avancer(10)
        self.assertIn('IR fraîche', self.b.t12.verifier_disponibilite(10))
        self.ouvrir_paiement()
        self.assertEqual(self.b.t12.verifier_disponibilite(10), '')
        self.assertEqual(self.b.t12._compteurs, {'bas': 0, 'sortie': 0})

    def test_trente_secondes_de_paiement_imposent_une_nouvelle_lecture(self):
        self.ouvrir_paiement()
        self.avancer(30)
        self.payer()
        self.assertEqual(self.b.can.envoyees, [(0x302, bytes([0xFF]))] * 2)
        self.assertEqual(self.b.comptes.consulter_compte(CARTE).solde_centimes, 800)
        self.aucune_commande_actionneur()
        self.b.can.synchroniser_ir()
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'PREPARATION')
        self.assertEqual(self.b.can.envoyees[-1][0], 0x120)

    def test_trames_deja_en_file_meme_horodatage_ne_satisfont_pas_lecture(self):
        self.b.can.synchroniser_ir()  # reçues mais pas encore traitées par T12
        self.confirmer()
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'VERIFICATION_IR')
        self.assertEqual(self.b.t12.lecture_ir.reponses, set())
        self.b.can.synchroniser_ir()
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'ATTENTE_PAIEMENT')

    def test_callback_commence_avant_demande_mais_retarde_par_verrou_est_ignore(self):
        from threading import Event, Thread, get_ident
        recu = Event()
        proprietaire = get_ident()
        def horloge_callback():
            valeur = self.b.horloge()
            if get_ident() != proprietaire:
                recu.set()
            return valeur
        self.b.t12.horloge = horloge_callback
        t = Thread(target=lambda: self.b.t12.traiter_trame(0x301, bytes([0, 2, 0, 1])))
        with self.b.t12._verrou_reception:
            t.start()
            self.addCleanup(t.join, 1)
            self.assertTrue(recu.wait(1))
            self.b.horloge.temps += .1
            self.confirmer()
        t.join(1)
        self.assertFalse(t.is_alive())
        self.b.can.emettre(0x311, [0, 0, 1])
        self.app.actualiser()
        self.assertEqual(self.b.t12.lecture_ir.reponses, {0x311})
        self.assertEqual(self.b.t04.gels, 0)
        self.b.can.synchroniser_ir()
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'ATTENTE_PAIEMENT')

    def test_evenements_seuls_ne_remplacent_pas_etats_complets(self):
        self.confirmer()
        self.b.can.ir_place(10, True)
        self.b.can.ir_sortie(False)
        self.app.actualiser()
        self.assertEqual(self.b.t12.lecture_ir.reponses, set())
        self.avancer(1)
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(self.b.t04.gels, 0)
        self.aucune_commande_actionneur()

    def test_repetition_confirmation_n_emet_pas_et_ne_prolonge_pas(self):
        self.confirmer()
        echeance = self.b.t12.lecture_ir.echeance
        self.avancer(.5)
        self.app.confirmer('r')
        self.assertEqual(self.b.t12.lecture_ir.echeance, echeance)
        self.assertEqual(self.b.can.envoyees, [(0x302, bytes([0xFF]))])
        self.avancer(.5)
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(self.b.t04.gels, 0)

    def test_reponse_partielle_et_doublons_n_etendent_pas_delai(self):
        self.confirmer()
        for _ in range(3):
            self.b.can.emettre(0x301, [0, 2, 0, 1])
            self.avancer(.25)
        self.avancer(.25)
        self.assertIn('0x311', self.app.vue().message)
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(self.b.t04.gels, 0)

    def test_reponse_exactement_a_echeance_refusee(self):
        self.confirmer()
        self.b.horloge.temps += 1
        self.b.can.synchroniser_ir()
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertIn('échéance', self.app.vue().message)

    def test_reponses_recues_a_temps_peuvent_etre_traitees_plus_tard(self):
        self.confirmer()
        self.b.horloge.temps += .9
        self.b.can.synchroniser_ir()
        self.b.horloge.temps += .2
        self.b.can.surveillance()
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'ATTENTE_PAIEMENT')

    def test_reponse_tardive_apres_echec_ne_relance_ni_paiement_ni_mouvement(self):
        self.confirmer()
        self.avancer(1)
        avant = list(self.b.can.envoyees)
        self.b.can.synchroniser_ir()
        self.app.actualiser()
        self.app.confirmer('r')
        self.app.actualiser()
        self.assertEqual(self.b.can.envoyees, avant)
        self.assertEqual(self.b.t04.gels, 0)
        self.assertTrue(self.b.t12.arbitre.bloque)

    def test_absence_reponse_apres_paiement_conserve_debit_sans_cloture(self):
        self.ouvrir_paiement(); self.payer()
        self.avancer(1)
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(self.b.comptes.consulter_compte(CARTE).solde_centimes, 800)
        self.assertEqual(self.b.t04.nombre_clotures, 0)
        self.aucune_commande_actionneur()
        avant = list(self.b.can.envoyees)
        self.b.can.synchroniser_ir()
        self.app.actualiser()
        self.assertEqual(self.b.can.envoyees, avant)

    def test_trames_invalides_verrouillent_meme_si_reponses_valides_suivent(self):
        for ident, donnees in ((0x301, [0, 2, 0, 0]), (0x311, [0, 0, 0]),
                               (0x301, [0, 0x42, 0, 1]), (0x311, [2, 0, 1]),
                               (0x301, [0, 2]), (0x300, [15, 1, 1])):
            with self.subTest(ident=ident, donnees=donnees):
                self.nouveau_banc()
                self.confirmer()
                self.b.can.emettre(ident, donnees)
                self.b.can.synchroniser_ir()
                self.app.actualiser()
                self.assertEqual(self.app.vue().phase, 'INTERROMPU')
                self.assertEqual(self.b.t04.gels, 0)
                self.assertTrue(self.b.t12.arbitre.bloque)
                self.aucune_commande_actionneur()

    def test_compteur_ancien_ne_compte_pas_comme_reponse(self):
        self.confirmer()
        self.b.can.emettre(0x301, [0, 2, 255, 1])
        self.b.can.emettre(0x311, [0, 0, 1])
        self.app.actualiser()
        self.assertEqual(self.b.t12.lecture_ir.reponses, {0x311})
        self.avancer(1)
        self.assertIn('0x301', self.app.vue().message)

    def test_annulation_pendant_lecture_n_ouvre_pas_paiement_ensuite(self):
        self.confirmer()
        self.assertEqual(self.app.annuler('r').phase, 'ANNULE')
        self.b.can.synchroniser_ir()
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'ANNULE')
        self.assertEqual(self.b.t04.gels, 0)
        self.aucune_commande_actionneur()

    def test_ancienne_reponse_en_file_apres_annulation_ne_valide_pas_nouvelle_demande(self):
        self.confirmer(); self.app.annuler('r')
        self.b.can.synchroniser_ir()
        self.confirmer('r2')
        self.app.actualiser()
        self.assertEqual(self.b.t12.lecture_ir.reponses, set())
        self.assertEqual(self.b.t04.gels, 0)
        self.b.can.synchroniser_ir()
        self.app.actualiser()
        self.assertEqual(self.app.vue().id_demande, 'r2')
        self.assertEqual(self.b.t04.gels, 1)

    def test_arret_can_pendant_lecture_interrompt_confirmation(self):
        self.confirmer()
        self.b.can.emettre(0x001, [1, 0, 0])
        self.b.can.synchroniser_ir()
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(self.b.t04.gels, 0)
        self.assertTrue(self.b.t12.arbitre.bloque)

    def test_heartbeat_initialisation_pendant_lecture_bloque(self):
        self.confirmer()
        self.b.can.emettre(0x041, [2, 0])
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(self.b.t04.gels, 0)

    def test_securite_perdue_pendant_attente_bloque(self):
        self.confirmer()
        self.b.securite.valeurs = replace(self.b.securite.valeurs, barriere_fermee=False)
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.aucune_commande_actionneur()

    def test_place_disparue_refuse_gel_sans_inventer_prise(self):
        self.confirmer()
        self.b.can.ir_place(10, False)
        self.b.can.synchroniser_ir()
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'ANNULE')
        self.assertEqual(self.b.t04.gels, 0)
        self.assertFalse(self.b.t12.place_liberee)
        self.aucune_commande_actionneur()

    def test_erreur_envoi_n_ouvre_pas_fenetre(self):
        self.app.demander(123456, 'r')
        with patch.object(self.b.can, 'envoyer', side_effect=OSError('bus indisponible')):
            self.app.confirmer('r')
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(self.b.t04.gels, 0)
        self.aucune_commande_actionneur()

    def test_service_differe_annule_avant_gel_et_autorise_lecture_apres_paiement(self):
        service = GestionServiceT13(ServiceRetraitSimule(self.b),
            self.b.racine / 'service.sqlite3', horloge=self.b.horloge)
        self.addCleanup(service.fermer)
        self.app.etat_service = lambda: service.etat
        service.traiter(nouvelle_commande('REMETTRE_EN_SERVICE'))
        self.confirmer()
        service.traiter(nouvelle_commande('METTRE_HORS_SERVICE'))
        self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'ANNULE')
        self.assertEqual(self.b.t04.gels, 0)
        service.traiter(nouvelle_commande('REMETTRE_EN_SERVICE'))
        self.confirmer('r2')
        self.b.can.synchroniser_ir(); self.app.actualiser()
        self.payer()
        service.traiter(nouvelle_commande('METTRE_HORS_SERVICE'))
        self.assertEqual(service.etat, 'MISE_HORS_SERVICE')
        self.b.can.synchroniser_ir(); self.app.actualiser()
        self.assertEqual(self.app.vue().phase, 'PREPARATION')

    def test_reinitialisation_apres_lecture_manquante_reste_hors_service_sans_reprise(self):
        adaptateur = ServiceRetraitSimule(self.b)
        service = GestionServiceT13(adaptateur, self.b.racine / 'service.sqlite3', horloge=self.b.horloge)
        self.addCleanup(service.fermer)
        self.app.etat_service = lambda: service.etat
        service.traiter(nouvelle_commande('REMETTRE_EN_SERVICE'))
        self.confirmer(); self.avancer(1)
        service.actualiser()
        self.assertEqual(service.etat, 'ARRET_VERROUILLE')
        avant = list(self.b.can.envoyees)
        adaptateur.intervention_simulee()
        service.traiter(nouvelle_commande('REINITIALISER'))
        self.b.horloge.temps += .6
        self.b.can.surveillance()
        service.actualiser(); self.app.actualiser(); service.actualiser()
        self.assertEqual(service.etat, 'HORS_SERVICE')
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(self.b.can.envoyees, avant)
        self.assertEqual(self.b.t04.gels, 0)

    @unittest.skipUnless(can is not None, 'python-can absent : essai CAN virtuel ignoré')
    def test_service_can_partage_et_callbacks_reels_sur_bus_virtuel(self):
        from communications.can_bus import ServiceCAN
        canal = 't12-ir-' + uuid4().hex
        service = ServiceCAN(interface='virtual', channel=canal)
        partenaire = can.Bus(interface='virtual', channel=canal)
        self.addCleanup(partenaire.shutdown)
        self.addCleanup(service.arreter)
        demandes = []
        def emettre(ident, data):
            partenaire.send(can.Message(arbitration_id=ident, data=data, is_extended_id=False))
        def recevoir(message):
            demandes.append((message.arbitration_id, bytes(message.data)))
            if message.arbitration_id == 0x302:
                emettre(0x301, [0, 2, 0, 1]); emettre(0x311, [0, 0, 1])
        reception = can.Notifier(partenaire, [recevoir])
        self.addCleanup(reception.stop)
        self.b.t12.fermer()
        self.b.t12 = creer_gestion_retrait(service, self.b.modele, self.b.t04,
            demande=self.b.demande, securite=self.b.securite,
            journal=self.b.racine / 'mecanique-virtuel.sqlite3',
            table_ir=TABLE_IR_SIMULEE, ordre_sortie='rotation_elevation', horloge=self.b.horloge)
        self.app.gestion = self.b.t12
        self.b.t12.autoriser_nouvelles(True)
        service.demarrer()
        emettre(0x041, [1, 1]); emettre(0x042, [1, 1])
        limite = time.monotonic() + 2
        while len(self.b.t12._hb) < 2 and time.monotonic() < limite:
            self.b.t12.mettre_a_jour(); time.sleep(.005)
        self.confirmer()
        limite = time.monotonic() + 2
        while self.app.vue().phase == 'VERIFICATION_IR' and time.monotonic() < limite:
            self.app.actualiser(); time.sleep(.005)
        self.assertEqual(self.app.vue().phase, 'ATTENTE_PAIEMENT')
        self.assertEqual(demandes, [(0x302, bytes([0xFF]))])
        self.assertEqual(self.b.t04.gels, 1)
        self.app.annuler('r')  # fin propre avant fermeture des transports


if __name__ == '__main__':
    unittest.main()
