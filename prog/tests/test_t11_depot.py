"""
test_t11_depot.py - T11 : tests de la séquence de dépôt (sans matériel).

Tests minimaux demandés (interface T11 v1.3, §10) : prise au niveau 0, dépôt IR
valide, début de facturation unique, absence IR, défaut CAN, retour mécanique.
Le STM32 Haut est remplacé par un « faux bus » qui répond à la main ;
un dernier test utilise le simulateur sur bus virtuel (si python-can).

Usage : python3 -m unittest prog/tests/test_t11_depot.py -v

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T11)
"""
from datetime import datetime
from pathlib import Path
import sys
import time
import unittest

RPI = Path(__file__).resolve().parents[1] / "rpi"
sys.path.insert(0, str(RPI))

from modules.depot import (EtapeDepot, GestionDepot, ID_BRAS_CMD,  # noqa: E402
                           ID_ELEVATION_CMD, ID_ROTATION_CMD, REPONSE_DE)
from modules.stationnement import EtatPlace, ModeleStationnement, Presence  # noqa: E402

try:
    import can  # noqa: F401
    CAN_DISPONIBLE = True
except ImportError:
    CAN_DISPONIBLE = False

HORODATAGE = datetime(2026, 11, 25, 14, 30, 0)


class Horloge:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FauxCAN:
    def __init__(self):
        self.envoyees = []

    def envoyer(self, identifiant, donnees):
        self.envoyees.append((identifiant, bytes(donnees)))

    @property
    def derniere(self):
        return self.envoyees[-1]


class TestDepot(unittest.TestCase):
    def setUp(self):
        self.can = FauxCAN()
        self.horloge = Horloge()
        self.factures = []
        self.modele = ModeleStationnement()
        for n in range(1, 15):
            self.modele.changer_presence(n, Presence.ABSENT)
        self.modele.changer_etat(10, EtatPlace.RESERVEE)          # E2.3 = niveau 2, position 3
        self.depot = GestionDepot(self.can, self.modele,
                                  lambda t, h: self.factures.append((t, h)),
                                  delai_ir_s=5.0, horloge=self.horloge,
                                  maintenant=lambda: HORODATAGE)

    # --------------------------------------------------------------- outils
    def repondre(self, resultat, donnees_etat=None, code=0):
        """Le STM32 Haut répond à la dernière commande envoyée."""
        ident, trame = self.can.derniere
        seq = trame[0]
        if ident == ID_BRAS_CMD:
            donnees = [seq, resultat, 1 if donnees_etat is None else donnees_etat, code]
        elif ident == ID_ELEVATION_CMD:
            donnees = [seq, resultat, 0 if donnees_etat is None else donnees_etat, code, 2]
        else:
            donnees = [seq, resultat, 0 if donnees_etat is None else donnees_etat, code]
        self.depot.traiter_trame(REPONSE_DE[ident], bytes(donnees))

    def executer_commande(self):
        """Mouvement normal : acceptée puis terminée (lecture : terminée directement)."""
        ident, trame = self.can.derniere
        lecture = trame[1] == (3 if ident == ID_BRAS_CMD else 2)
        if not lecture:
            self.repondre(1)
        self.repondre(2)

    def avancer_jusqu_a(self, action_finale):
        """Exécute les commandes jusqu'à envoyer (sans la répondre) celle qui vérifie action_finale."""
        for _ in range(20):
            if action_finale(*self.can.derniere):
                return
            self.executer_commande()
        self.fail("commande attendue jamais envoyée")

    def ir(self, present=True):
        self.depot.traiter_trame(0x300, bytes([9, 1 if present else 0, 1]))   # indice 9 = E2.3

    # ------------------------------------------------------------ préconditions
    def test_refus_sans_reservation_ou_parametres(self):
        self.assertFalse(self.depot.demarrer(1, 1, 1))              # place 1 non réservée
        self.assertFalse(self.depot.demarrer(1, 3, 1))
        self.assertFalse(self.depot.demarrer(1, 2, 8))
        self.modele.changer_presence(10, Presence.PRESENT)
        self.assertFalse(self.depot.demarrer(1, 2, 3))
        self.assertEqual(self.can.envoyees, [])

    def test_une_seule_operation(self):
        self.assertTrue(self.depot.demarrer(1, 2, 3))
        self.assertFalse(self.depot.demarrer(2, 2, 3))

    def test_preparation_refusee_si_bras_deploye(self):
        self.depot.demarrer(1, 2, 3)
        self.assertEqual(self.can.derniere, (ID_BRAS_CMD, bytes([1, 3, 0])))   # lecture du bras
        self.repondre(2, donnees_etat=2)                                       # déployé
        self.assertEqual(self.depot.etape, EtapeDepot.DEFAUT)
        self.assertIn("bras non rétracté", self.depot.obtenir_etat())

    # ----------------------------------------------------------- séquence nominale
    def test_sequence_complete_et_facturation_unique(self):
        self.assertTrue(self.depot.demarrer(4213, 2, 3))
        actions = []
        while self.depot.etape != EtapeDepot.TERMINE:
            ident, trame = self.can.derniere
            actions.append((ident, trame[1], trame[2]))
            if ident == ID_ELEVATION_CMD and trame[1] == 4:           # abaissement
                self.repondre(1)
                self.ir(True)                                          # présence confirmée
                self.ir(True)                                          # répétition
                self.repondre(2)
                continue
            self.executer_commande()
            self.assertLess(len(actions), 20)

        self.assertEqual(actions, [
            (ID_BRAS_CMD, 3, 0), (ID_ELEVATION_CMD, 2, 0), (ID_ROTATION_CMD, 2, 0xFF),  # préparation
            (ID_BRAS_CMD, 1, 0), (ID_ELEVATION_CMD, 3, 0), (ID_BRAS_CMD, 2, 0),         # prise niveau 0
            (ID_ELEVATION_CMD, 1, 2), (ID_ROTATION_CMD, 1, 3),                         # transport
            (ID_BRAS_CMD, 1, 0), (ID_ELEVATION_CMD, 4, 0),                             # dépôt
            (ID_BRAS_CMD, 2, 0), (ID_ROTATION_CMD, 1, 0), (ID_ELEVATION_CMD, 1, 0),     # retour
        ])
        self.assertEqual(self.factures, [(4213, HORODATAGE)])
        self.assertEqual(self.modele.etat(10), EtatPlace.OCCUPEE)
        self.assertEqual(self.modele.presence(10), Presence.PRESENT)
        self.assertTrue(self.depot.depot_confirme and self.depot.sequence_terminee)

    def test_ir_pendant_retour_et_retour_avant_ir(self):
        self.depot.demarrer(1, 2, 3)
        self.avancer_jusqu_a(lambda i, t: i == ID_ELEVATION_CMD and t[1] == 4)
        self.executer_commande()                                       # abaissement terminé sans IR
        for _ in range(5):                                             # retour complet
            if self.depot.sequence_terminee:
                break
            self.executer_commande()
        self.assertTrue(self.depot.sequence_terminee)
        self.assertEqual(self.depot.etape, EtapeDepot.RETOUR)          # attend encore l'IR
        self.assertEqual(self.factures, [])
        self.horloge.t += 3
        self.ir(True)
        self.assertEqual(self.depot.etape, EtapeDepot.TERMINE)
        self.assertEqual(len(self.factures), 1)

    def test_ir_avant_abaissement_ignore(self):
        self.depot.demarrer(1, 2, 3)
        self.avancer_jusqu_a(lambda i, t: i == ID_ROTATION_CMD and t[1] == 1 and t[2] == 3)
        self.ir(True)                                                  # trop tôt : pas un dépôt
        self.assertEqual(self.factures, [])
        self.assertFalse(self.depot.depot_confirme)

    # -------------------------------------------------------------- anomalies
    def test_absence_ir_apres_abaissement(self):
        self.depot.demarrer(1, 2, 3)
        self.avancer_jusqu_a(lambda i, t: i == ID_ELEVATION_CMD and t[1] == 4)
        self.executer_commande()                                       # abaissement terminé
        self.executer_commande()                                       # rétraction : le retour continue
        self.horloge.t += 5.1                                          # rotation sans réponse IR
        self.repondre(1)
        self.depot.mettre_a_jour()
        self.assertEqual(self.depot.etape, EtapeDepot.DEFAUT)
        self.assertIn("aucune présence IR", self.depot.derniere_erreur)
        self.assertEqual(self.factures, [])
        self.assertEqual(self.modele.etat(10), EtatPlace.DEFAUT)
        nb = len(self.can.envoyees)
        self.executer_commande()                                       # réponses tardives
        self.assertEqual(len(self.can.envoyees), nb)                   # aucune relance

    def test_commande_refusee(self):
        self.depot.demarrer(1, 2, 3)
        self.avancer_jusqu_a(lambda i, t: i == ID_ROTATION_CMD and t[1] == 1)
        self.repondre(0, code=1)
        self.assertEqual(self.depot.etape, EtapeDepot.DEFAUT)
        self.assertIn("refusée", self.depot.obtenir_etat())

    def test_pas_de_reponse(self):
        self.depot.demarrer(1, 2, 3)
        self.horloge.t += 1.1
        self.depot.mettre_a_jour()
        self.assertEqual(self.depot.etape, EtapeDepot.DEFAUT)
        self.assertIn("aucune réponse", self.depot.derniere_erreur)

    def test_mouvement_trop_long_envoie_arret(self):
        self.depot.demarrer(1, 2, 3)
        self.avancer_jusqu_a(lambda i, t: i == ID_BRAS_CMD and t[1] == 1)
        self.repondre(1)
        self.horloge.t += 31
        self.depot.mettre_a_jour()
        self.assertEqual(self.depot.etape, EtapeDepot.DEFAUT)
        self.assertEqual(self.can.derniere[0], ID_BRAS_CMD)
        self.assertEqual(self.can.derniere[1][1], 0)                   # action arrêt

    def test_defaut_moteur_et_arret_can(self):
        self.depot.demarrer(1, 2, 3)
        self.avancer_jusqu_a(lambda i, t: i == ID_ELEVATION_CMD and t[1] == 1)
        self.repondre(1)
        self.repondre(4, code=7)
        self.assertEqual(self.depot.etape, EtapeDepot.DEFAUT)

    def test_arret_haut_interrompt(self):
        self.depot.demarrer(1, 2, 3)
        self.executer_commande()
        self.depot.traiter_trame(0x001, bytes([2, 1, 0]))
        self.assertEqual(self.depot.etape, EtapeDepot.INTERROMPU)
        nb = len(self.can.envoyees)
        self.depot.mettre_a_jour()
        self.assertEqual(len(self.can.envoyees), nb)

    def test_defaut_doit_etre_acquitte(self):
        self.depot.demarrer(1, 2, 3)
        self.repondre(0)
        self.assertFalse(self.depot.demarrer(1, 2, 3))
        self.assertTrue(self.depot.acquitter_defaut())
        self.assertTrue(self.depot.demarrer(1, 2, 3))

    def test_ir_complet_masque(self):
        self.depot.demarrer(1, 2, 3)
        self.avancer_jusqu_a(lambda i, t: i == ID_ELEVATION_CMD and t[1] == 4)
        self.repondre(1)
        self.depot.traiter_trame(0x301, bytes([0, 1 << 1, 5, 0]))     # bit 9, mais non fiable
        self.assertFalse(self.depot.depot_confirme)
        self.depot.traiter_trame(0x301, bytes([0, 1 << 1, 6, 1]))     # valide
        self.assertTrue(self.depot.depot_confirme)


@unittest.skipUnless(CAN_DISPONIBLE, "python-can non installé")
class TestBusVirtuel(unittest.TestCase):
    """T11 + ServiceCAN + ascenseur simulé : séquence réelle sur bus virtuel."""

    def _executer(self, ir_actif):
        from communications.can_bus import ServiceCAN
        from exemples.simulateur_ascenseur import SimulateurAscenseur
        from modules.depot import creer_gestion_depot

        modele = ModeleStationnement()
        for n in range(1, 15):
            modele.changer_presence(n, Presence.ABSENT)
        modele.changer_etat(5, EtatPlace.RESERVEE)                     # E1.5
        factures = []
        canal = f"test-t11-{ir_actif}"
        sim = SimulateurAscenseur(channel=canal, duree_mouvement_s=0.05, ir_actif=ir_actif)
        service = ServiceCAN(interface="virtual", channel=canal)
        sim.demarrer()
        try:
            depot = creer_gestion_depot(service, modele, lambda t, h: factures.append(t),
                                        delai_ir_s=0.5)
            service.demarrer()
            self.assertTrue(depot.demarrer(777, 1, 5))
            limite = time.monotonic() + 5
            while depot.occupe and time.monotonic() < limite:
                depot.mettre_a_jour()
                time.sleep(0.02)
            return depot, modele, factures, sim
        finally:
            service.arreter()
            sim.arreter()

    def test_depot_complet(self):
        depot, modele, factures, sim = self._executer(ir_actif=True)
        self.assertEqual(depot.etape, EtapeDepot.TERMINE, depot.obtenir_etat())
        self.assertEqual(factures, [777])
        self.assertEqual(modele.etat(5), EtatPlace.OCCUPEE)
        self.assertEqual((sim.niveau, sim.angle, sim.bras), (0, 0, 1))  # retour au niveau 0

    def test_anomalie_ir(self):
        depot, modele, factures, _ = self._executer(ir_actif=False)
        self.assertEqual(depot.etape, EtapeDepot.DEFAUT)
        self.assertEqual(factures, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
