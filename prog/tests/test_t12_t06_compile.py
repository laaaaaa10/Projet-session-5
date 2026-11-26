"""Interopérabilité T12 ↔ t06_ir.c livré ; périphériques et transport simulés."""
from functools import partial
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

PROG = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROG / 'rpi'), str(PROG)]

from application.integration_t12 import RaccordementRetrait, LecteurGardeRetrait
from commun.t13.protocole import nouvelle_commande
from exemples.banc_retrait import BancRetrait, CARTE
from exemples.banc_retrait_t06 import compiler_t06, BusRetraitCodeT06
from exemples.service_retrait_simule import ServiceRetraitSimule
from modules.lecteur_nfc_rfid import EvenementRFID
from modules.service_t13 import GestionServiceT13
from modules.stationnement import EtatPlace, Presence


@unittest.skipUnless(shutil.which('cc') or shutil.which('gcc'), 'Compilateur C requis : essai non validé')
class TestsT12CodeT06(unittest.TestCase):
    def creer_banc(self, **options):
        dossier = TemporaryDirectory(prefix='esa-t12-t06-')
        self.addCleanup(dossier.cleanup)
        bibliotheque = compiler_t06(dossier.name)
        self.b = BancRetrait(dossier.name, fabrique_can=partial(
            BusRetraitCodeT06, bibliotheque=bibliotheque, **options))
        self.service = GestionServiceT13(ServiceRetraitSimule(self.b),
            Path(dossier.name) / 'service.sqlite3', horloge=self.b.horloge)
        self.app = RaccordementRetrait(self.b.t12, t04=self.b.t04,
                                      etat_service=lambda: self.service.etat)
        self.addCleanup(self.service.fermer)
        self.addCleanup(self.app.fermer)
        self.service.traiter(nouvelle_commande('REMETTRE_EN_SERVICE'))
        self.assertEqual(self.service.etat, 'EN_SERVICE')

    def actualiser(self):
        self.app.actualiser()
        self.service.actualiser()

    def confirmer(self):
        self.assertEqual(self.app.demander(123456, 'r').phase, 'DEMANDE')
        self.assertEqual(self.app.confirmer('r').phase, 'VERIFICATION_IR')
        self.assertEqual(self.b.t04.gels, 0)
        self.actualiser()

    def payer(self):
        self.assertEqual(self.app.vue().phase, 'ATTENTE_PAIEMENT')
        lecteur = SimpleNamespace(lire=lambda: [EvenementRFID('ACCEPTE', 'banc', CARTE)])
        self.b.borne.actualiser(LecteurGardeRetrait(lecteur, self.app), t04=self.b.t04)
        self.app.actualiser()  # observer la demande avant le prochain traitement de réception
        self.assertEqual(self.app.vue().phase, 'VERIFICATION_IR_APRES_PAIEMENT')
        self.assertEqual(self.b.comptes.consulter_compte(CARTE).solde_centimes, 800)

    def commandes_mecaniques(self):
        return [trame for trame in self.b.can.envoyees if trame[0] in (0x100, 0x110, 0x120)]

    def test_cycle_complet_30_secondes_et_cloture_unique(self):
        self.creer_banc()
        self.confirmer()
        for _ in range(60):
            self.b.tour(.5)
            self.actualiser()
        self.payer()
        self.assertEqual(self.commandes_mecaniques(), [])
        complets = [d for _, i, d in self.b.can.trace_bas if i == 0x301]
        self.assertEqual(complets[-2:], [bytes([0, 2, 0, 1])] * 2)
        self.actualiser()
        self.assertEqual(self.app.vue().phase, 'PREPARATION')
        self.service.traiter(nouvelle_commande('METTRE_HORS_SERVICE'))
        for _ in range(40):
            if self.app.vue().phase == 'ATTENTE_RETRAIT_MANUEL':
                break
            self.b.mouvement()
            self.actualiser()
        self.assertEqual(self.app.vue().phase, 'ATTENTE_RETRAIT_MANUEL')
        self.assertIn((0x300, bytes([9, 0, 1])), [(i, d) for _, i, d in self.b.can.trace_bas])
        self.assertEqual(self.b.modele.presence(10), Presence.ABSENT)
        self.assertEqual(self.b.modele.etat(10), EtatPlace.OCCUPEE)
        self.assertEqual(self.b.t04.nombre_clotures, 0)
        self.assertEqual(self.service.etat, 'MISE_HORS_SERVICE')
        self.b.can.ir_sortie(False)
        self.actualiser()
        self.assertEqual(self.app.vue().phase, 'TERMINE')
        self.assertEqual(self.service.etat, 'HORS_SERVICE')
        self.assertEqual(self.b.modele.etat(10), EtatPlace.LIBRE)
        commandes = self.commandes_mecaniques()
        self.app.confirmer('r')
        self.b.can.synchroniser_ir()
        self.b.can.ir_sortie(False)
        self.actualiser()
        self.assertEqual(self.b.t04.nombre_clotures, 1)
        self.assertEqual(self.commandes_mecaniques(), commandes)

    def test_haut_absent_avant_paiement_ne_gele_pas_et_ne_demarre_pas(self):
        self.creer_banc()
        self.b.can.haut_actif = False
        self.confirmer()
        self.assertEqual(self.b.t12.lecture_ir.reponses, {0x301})
        self.b.tour(1)
        self.actualiser()
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertIn('0x311', self.app.vue().message)
        self.assertEqual(self.service.etat, 'ARRET_VERROUILLE')
        self.assertEqual(self.b.t04.gels, 0)
        self.assertEqual(self.b.comptes.consulter_compte(CARTE).solde_centimes, 1000)
        self.assertEqual(self.commandes_mecaniques(), [])
        self.b.can.haut_actif = True
        self.b.can.synchroniser_ir()
        self.actualiser()
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(self.b.t04.gels, 0)

    def test_haut_absent_apres_paiement_conserve_debit_sans_mouvement(self):
        self.creer_banc()
        self.confirmer()
        self.b.can.haut_actif = False
        self.payer()
        self.b.tour(1)
        self.actualiser()
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(self.service.etat, 'ARRET_VERROUILLE')
        self.assertEqual(self.b.t04.nombre_clotures, 0)
        self.assertEqual(self.b.modele.etat(10), EtatPlace.OCCUPEE)
        self.assertEqual(self.commandes_mecaniques(), [])
        self.assertEqual(self.b.comptes.consulter_compte(CARTE).solde_centimes, 800)

    def test_bas_non_valide_au_demarrage_est_refuse(self):
        self.creer_banc(valider_demarrage=False)
        self.confirmer()
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(self.b.can.trace_bas[-1][2][-1], 0)
        self.assertEqual(self.b.t04.gels, 0)
        self.assertEqual(self.commandes_mecaniques(), [])

    def test_une_seule_pcb04_ne_valide_pas_les_quatorze_places(self):
        self.creer_banc(nb_cartes=1)
        self.confirmer()
        self.assertEqual(self.app.vue().phase, 'INTERROMPU')
        self.assertEqual(self.b.t04.gels, 0)
        self.assertEqual(self.commandes_mecaniques(), [])
        self.assertEqual(self.b.modele.presence(10), Presence.INCONNU)

    def test_erreur_carte_pendant_mecanique_arrete_sans_reprise(self):
        self.creer_banc()
        self.confirmer()
        self.payer()
        self.actualiser()
        self.b.can.t06.erreurs[1] = True
        self.b.tour(.25)
        self.actualiser()
        self.assertEqual(self.service.etat, 'ARRET_VERROUILLE')
        self.assertIn(self.app.vue().phase, ('DEFAUT', 'INTERROMPU'))
        self.assertEqual(self.b.modele.presence(10), Presence.INCONNU)
        commandes = list(self.b.can.envoyees)
        self.b.can.t06.erreurs[1] = False
        self.b.tour(.25)
        self.actualiser()
        self.assertEqual(self.b.can.envoyees, commandes)
        self.assertEqual(self.b.t04.nombre_clotures, 0)

    def test_indices_des_deux_cartes_aboutissent_aux_bonnes_places_t12(self):
        self.creer_banc()
        self.b.can.ir_place(10, False)
        self.b.tour(.25)
        for carte in range(2):
            for circuit in range(7):
                with self.subTest(carte=carte, circuit=circuit):
                    place = (carte + 1) * 7 - circuit  # relevé de câblage, indépendant de la table C
                    self.b.can.t06.vehicules[carte][circuit] = True
                    self.b.tour(.25)
                    self.assertEqual(self.b.modele.presence(place), Presence.PRESENT)
                    self.assertEqual([p for p in range(1, 15)
                        if self.b.modele.presence(p) == Presence.PRESENT], [place])
                    self.b.can.t06.vehicules[carte][circuit] = False
                    self.b.tour(.25)
        self.assertEqual(self.b.t12.derniere_erreur, '')

    def test_impulsion_courte_ne_change_pas_presence_t12(self):
        self.creer_banc()
        avant = list(self.b.can.trace_bas)
        self.b.can.ir_place(10, False)
        self.b.tour(.030)
        self.b.can.ir_place(10, True)
        self.b.tour(.25)
        self.assertEqual(self.b.modele.presence(10), Presence.PRESENT)
        self.assertEqual(self.b.can.trace_bas, avant)

    def test_passage_du_bras_ne_se_fait_pas_passer_pour_la_rampe(self):
        self.creer_banc()
        avant = list(self.b.can.trace_bas)
        self.b.can.t06.vehicules[0][7] = True
        self.b.can.t06.vehicules[1][7] = True
        self.b.tour(.25)
        self.assertEqual(self.b.can.trace_bas, avant)
        self.assertIs(self.b.t12.sortie, False)
        self.assertFalse(self.b.t12.arrivee_sortie)
        self.assertFalse(self.b.t12.depart_confirme)


if __name__ == '__main__':
    unittest.main()
