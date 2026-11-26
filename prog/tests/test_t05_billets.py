"""
test_t05_billets.py - T05 : tests automatiques côté RPi (sans matériel).

  - GestionBillets : séquences, états, délai sans réponse, réponses tardives
  - LecteurCodeBarres.traiter_saisie : format du numéro à six chiffres
  - Service CAN commun + STM32 Borne simulé sur un bus virtuel (si python-can)

Usage : python3 -m unittest prog/tests/test_t05_billets.py -v

Projet ESA - 243-557 - Automne 2026
"""
from datetime import datetime
from pathlib import Path
import struct
import sys
import time
import unittest

RPI = Path(__file__).resolve().parents[1] / "rpi"
sys.path.insert(0, str(RPI))

from modules.billets import (ID_IMPRESSION_CMD, ID_IMPRESSION_DATE,  # noqa: E402
                             ID_IMPRESSION_ETAT, EtatImpression, GestionBillets)
from modules.lecteur_code_barres import LecteurCodeBarres  # noqa: E402

try:
    import can  # noqa: F401
    CAN_DISPONIBLE = True
except ImportError:
    CAN_DISPONIBLE = False


class Horloge:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class TestGestionBillets(unittest.TestCase):
    def setUp(self):
        self.trames = []
        self.horloge = Horloge()
        self.gb = GestionBillets(lambda i, d: self.trames.append((i, d)),
                                 delai_reponse_s=5.0, horloge=self.horloge)

    def test_trames_conformes_au_protocole(self):
        seq = self.gb.demander_impression(4213, 3, datetime(2026, 11, 19, 13, 45, 7))
        (id1, cmd), (id2, date) = self.trames
        self.assertEqual((id1, id2), (ID_IMPRESSION_CMD, ID_IMPRESSION_DATE))
        self.assertEqual(cmd, struct.pack("<BBIBB", seq, 1, 4213, 3, 0))
        self.assertEqual(date, bytes([seq, 26, 11, 19, 13, 45, 7]))
        self.assertEqual(cmd[2:6], bytes([0x75, 0x10, 0, 0]))      # little-endian

    def test_sequences_successives(self):
        s1 = self.gb.demander_impression(1, 1, datetime.now())
        s2 = self.gb.demander_impression(2, 2, datetime.now())
        self.assertEqual(s2, (s1 + 1) % 256)

    def test_validation_avant_envoi(self):
        with self.assertRaises(ValueError):
            self.gb.demander_impression(1_000_000, 1, datetime.now())
        with self.assertRaises(ValueError):
            self.gb.demander_impression(1, 15, datetime.now())
        self.assertEqual(self.trames, [])

    def test_succes(self):
        seq = self.gb.demander_impression(1, 1, datetime.now())
        self.assertEqual(self.gb.etat_brut(seq), EtatImpression.EN_ATTENTE)
        self.gb.traiter_trame(ID_IMPRESSION_ETAT, bytes([seq, 1, 0]))
        self.assertEqual(self.gb.etat_brut(seq), EtatImpression.VALIDEE)
        self.gb.traiter_trame(ID_IMPRESSION_ETAT, bytes([seq, 2, 0]))
        self.assertEqual(self.gb.etat_brut(seq), EtatImpression.ENVOYEE)

    def test_refus_avec_code(self):
        seq = self.gb.demander_impression(1, 1, datetime.now())
        self.gb.traiter_trame(ID_IMPRESSION_ETAT, bytes([seq, 0, 0x07]))
        self.assertEqual(self.gb.obtenir_etat(seq), "refusée (imprimante occupée)")

    def test_autres_sequences_et_trames_ignorees(self):
        seq = self.gb.demander_impression(1, 1, datetime.now())
        self.gb.traiter_trame(ID_IMPRESSION_ETAT, bytes([(seq + 1) % 256, 2, 0]))
        self.gb.traiter_trame(0x300, bytes([seq, 2, 0]))
        self.gb.traiter_trame(ID_IMPRESSION_ETAT, bytes([seq, 2]))   # DLC invalide
        self.assertEqual(self.gb.etat_brut(seq), EtatImpression.EN_ATTENTE)

    def test_sans_reponse(self):
        seq = self.gb.demander_impression(1, 1, datetime.now())
        self.horloge.t += 4.9
        self.gb.mettre_a_jour()
        self.assertEqual(self.gb.etat_brut(seq), EtatImpression.EN_ATTENTE)
        self.horloge.t += 0.2
        self.gb.mettre_a_jour()
        self.assertEqual(self.gb.etat_brut(seq), EtatImpression.SANS_REPONSE)

    def test_reponse_tardive_ignoree(self):
        seq = self.gb.demander_impression(1, 1, datetime.now())
        self.gb.traiter_trame(ID_IMPRESSION_ETAT, bytes([seq, 2, 0]))
        self.gb.traiter_trame(ID_IMPRESSION_ETAT, bytes([seq, 3, 0x08]))
        self.assertEqual(self.gb.etat_brut(seq), EtatImpression.ENVOYEE)


class TestSaisieNumero(unittest.TestCase):
    def test_formats(self):
        valider = LecteurCodeBarres.traiter_saisie
        self.assertEqual(valider("123456"), 123456)
        self.assertEqual(valider(" 004213\r\n"), 4213)
        for invalide in ("12345", "1234567", "12a456", "^B123456", "", None):
            self.assertIsNone(valider(invalide))


@unittest.skipUnless(CAN_DISPONIBLE, "python-can non installé")
class TestBusVirtuel(unittest.TestCase):
    """Chaîne complète : ServiceCAN → STM32 Borne simulé → réponses 0x230."""

    def test_impression_de_bout_en_bout(self):
        from communications.can_bus import ServiceCAN
        from exemples.simulateur_stm32_borne import SimulateurStm32Borne
        from modules.billets import creer_gestion_billets

        simulateur = SimulateurStm32Borne(channel="test-t05", duree_impression_s=0.2)
        service = ServiceCAN(interface="virtual", channel="test-t05")
        simulateur.demarrer()
        try:
            billets = creer_gestion_billets(service)
            service.demarrer()
            seq = billets.demander_impression(123456, 12, datetime.now())
            limite = time.monotonic() + 3
            while not billets.etat_brut(seq).est_finale and time.monotonic() < limite:
                time.sleep(0.02)
            self.assertEqual(billets.etat_brut(seq), EtatImpression.ENVOYEE)
        finally:
            service.arreter()
            simulateur.arreter()


if __name__ == "__main__":
    unittest.main(verbosity=2)
