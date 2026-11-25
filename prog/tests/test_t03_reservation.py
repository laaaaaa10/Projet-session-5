"""
test_t03_reservation.py - T03 : tests automatiques de la réservation (sans matériel).

Usage : python3 -m unittest prog/tests/test_t03_reservation.py -v

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T03)
"""
from pathlib import Path
import sys
import unittest

RPI = Path(__file__).resolve().parents[1] / "rpi"
sys.path.insert(0, str(RPI))

from modules.reservation import (GestionReservation, TARIF_CENTIMES_PAR_MINUTE,  # noqa: E402
                                 evaluer_carte)
from modules.stationnement import (EtatPlace, ModeleStationnement, Presence,  # noqa: E402
                                   libelle_place, numero_place)


class Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TestReservation(unittest.TestCase):
    def setUp(self):
        self.horloge = Horloge()
        self.modele = ModeleStationnement()
        for n in range(1, 15):
            self.modele.changer_presence(n, Presence.ABSENT)
        self.transactions = []
        self.conditions = (True, "")

        def creer(numero, session_id):
            self.transactions.append((numero, session_id))
            return 100000 + len(self.transactions)

        self.gr = GestionReservation(self.modele, creer,
                                     verifier_conditions=lambda: self.conditions,
                                     horloge=self.horloge)

    # --- affichage
    def test_14_places_et_libelles(self):
        places = self.gr.obtenir_places()
        self.assertEqual(len(places), 14)
        self.assertIn("E1.1", places)
        self.assertIn("E2.7", places)
        self.assertEqual(libelle_place(12), "E2.5")
        self.assertEqual(numero_place("E2.5"), 12)

    def test_place_occupee_non_selectionnable(self):
        self.modele.changer_etat(3, EtatPlace.OCCUPEE)
        self.assertFalse(self.gr.obtenir_places()["E1.3"]["selectionnable"])
        self.assertFalse(self.gr.reserver_place("E1.3", "s1"))

    def test_presence_physique_bloque(self):
        self.modele.changer_presence(5, Presence.PRESENT)    # libre mais voiture détectée
        self.assertFalse(self.gr.reserver_place("E1.5", "s1"))
        self.modele.changer_presence(6, Presence.INCONNU)    # capteur non fiable
        self.assertFalse(self.gr.reserver_place("E1.6", "s1"))

    # --- réservation
    def test_reservation_verrouille(self):
        self.assertTrue(self.gr.reserver_place("E1.2", "s1"))
        self.assertEqual(self.modele.etat(2), EtatPlace.RESERVEE)

    def test_conflit_deux_sessions(self):
        self.assertTrue(self.gr.reserver_place("E1.2", "s1"))
        self.assertFalse(self.gr.reserver_place("E1.2", "s2"))

    def test_changement_de_place(self):
        self.gr.reserver_place("E1.2", "s1")
        self.assertTrue(self.gr.reserver_place("E1.4", "s1"))
        self.assertEqual(self.modele.etat(2), EtatPlace.LIBRE)
        self.assertEqual(self.modele.etat(4), EtatPlace.RESERVEE)

    # --- délai de 60 s
    def test_expiration_libere(self):
        self.gr.reserver_place("E1.2", "s1")
        self.horloge.t += 59.9
        self.assertEqual(self.gr.mettre_a_jour(), [])
        self.horloge.t += 0.2
        self.assertEqual(self.gr.mettre_a_jour(), ["s1"])
        self.assertEqual(self.modele.etat(2), EtatPlace.LIBRE)
        self.assertIsNone(self.gr.confirmer_depot("s1"))

    def test_confirmation_annule_le_delai(self):
        self.gr.reserver_place("E1.2", "s1")
        self.assertEqual(self.gr.confirmer_depot("s1"), 100001)
        self.horloge.t += 120
        self.gr.mettre_a_jour()
        self.gr.expiration_reservation("s1")                 # libération tardive refusée
        self.assertEqual(self.modele.etat(2), EtatPlace.RESERVEE)

    # --- annulation
    def test_annulation(self):
        self.gr.reserver_place("E1.2", "s1")
        self.assertTrue(self.gr.annuler_reservation("s1"))
        self.assertEqual(self.modele.etat(2), EtatPlace.LIBRE)

    def test_annulation_apres_confirmation_refusee(self):
        self.gr.reserver_place("E1.2", "s1")
        self.gr.confirmer_depot("s1")
        self.assertFalse(self.gr.annuler_reservation("s1"))
        self.assertEqual(self.modele.etat(2), EtatPlace.RESERVEE)

    # --- confirmation
    def test_confirmation_conditions(self):
        self.gr.reserver_place("E1.2", "s1")
        self.conditions = (False, "système hors service")
        self.assertIsNone(self.gr.confirmer_depot("s1"))
        self.assertEqual(self.gr.derniere_raison, "système hors service")
        self.assertEqual(self.transactions, [])              # T04 pas appelé

    def test_confirmation_etat_perime(self):
        self.gr.reserver_place("E1.2", "s1")
        self.modele.changer_presence(2, Presence.PRESENT)    # voiture apparue entre-temps
        self.assertIsNone(self.gr.confirmer_depot("s1"))

    def test_confirmation_unique(self):
        self.gr.reserver_place("E1.2", "s1")
        t1 = self.gr.confirmer_depot("s1")
        t2 = self.gr.confirmer_depot("s1")                   # double clic
        self.assertEqual(t1, t2)
        self.assertEqual(len(self.transactions), 1)

    def test_t04_recoit_place_et_session(self):
        self.gr.reserver_place("E2.5", "depot-7")
        self.gr.confirmer_depot("depot-7")
        self.assertEqual(self.transactions, [(12, "depot-7")])

    def test_t04_refuse(self):
        gr = GestionReservation(self.modele, lambda n, s: None, horloge=self.horloge)
        gr.reserver_place("E1.2", "s1")
        self.assertIsNone(gr.confirmer_depot("s1"))
        self.assertEqual(self.modele.etat(2), EtatPlace.RESERVEE)   # reste à confirmer


class TestCarte(unittest.TestCase):
    """Identification au dépôt : solde, tarif et durée maximale (énoncé ESA)."""

    def test_carte_connue(self):
        info = evaluer_carte("11008827F9", 2000)
        self.assertTrue(info.acceptee)
        self.assertEqual(info.duree_max_min, 2000 // TARIF_CENTIMES_PAR_MINUTE)

    def test_carte_inconnue(self):
        info = evaluer_carte("AABBCCDDEE", None)
        self.assertFalse(info.acceptee)
        self.assertEqual(info.raison, "carte inconnue")

    def test_solde_nul_n_est_pas_inconnu(self):
        info = evaluer_carte("11008827F9", 0)
        self.assertFalse(info.acceptee)
        self.assertEqual(info.raison, "solde insuffisant")

    def test_minute_commencee(self):
        self.assertEqual(evaluer_carte("11008827F9", TARIF_CENTIMES_PAR_MINUTE * 3 + 9).duree_max_min, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
