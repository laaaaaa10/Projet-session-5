"""Tests RFID sur PC, sans serial/gpiozero ni materiel.

Depuis la racine :
python3 -m unittest discover -s prog/tests -p 'test_rfid_integration.py' -v
"""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

RPI = Path(__file__).resolve().parents[1] / "rpi"
sys.path.insert(0, str(RPI))
from modules import lecteur_nfc_rfid as rfid
import main as borne


BADGE_A = b"\x02110082373490\r\n\x03"
BADGE_B = b"\x0211008827F947\r\n\x03"
BADGE_C = b"\x021100880F2DBB\r\n\x03"


class FauxUART:
    def __init__(self, banc):
        self.banc = banc
        self.tampon = bytearray()

    @property
    def in_waiting(self):
        return len(self.tampon)

    def read(self, taille):
        self.banc.tailles_lues.append(taille)
        if self.banc.erreur_lecture:
            raise OSError("UART deconnecte")
        donnees = bytes(self.tampon[:taille])
        del self.tampon[:taille]
        return donnees

    def reset_input_buffer(self):
        if self.banc.erreur_vidage:
            raise OSError("Vidage UART impossible")
        self.tampon.clear()

    def close(self):
        self.banc.fermetures.append("uart")


class FauxRNG:
    def __init__(self, banc):
        self.banc = banc
        self.is_active = banc.initial
        self.when_activated = None
        self.when_deactivated = None

    def definir(self, presente):
        if presente != self.is_active:
            self.is_active = presente
            callback = self.when_activated if presente else self.when_deactivated
            if callback is not None:
                callback()

    def close(self):
        self.when_activated = None
        self.when_deactivated = None
        self.banc.fermetures.append("rng")


class BancSimule:
    def __init__(self, initial=False):
        self.maintenant = 0.0
        self.initial = initial
        self.fermetures = []
        self.chips = []
        self.tailles_lues = []
        self.erreur_ouverture = False
        self.erreur_vidage = False
        self.erreur_lecture = False

    def creer_fabrique(self, *, chip):
        self.chips.append(chip)
        return SimpleNamespace(close=lambda: self.fermetures.append("fabrique"))

    def creer_rng(self, gpio, **options):
        self.gpio, self.options_gpio = gpio, options
        self.rng = FauxRNG(self)
        return self.rng

    def creer_uart(self, port, **options):
        self.port, self.options_uart = port, options
        if self.erreur_ouverture:
            raise OSError("Port UART inaccessible")
        self.uart = FauxUART(self)
        return self.uart

    def installer(self, ressources):
        modules = {
            "serial": SimpleNamespace(Serial=self.creer_uart, EIGHTBITS=8,
                                      PARITY_NONE="N", STOPBITS_ONE=1),
            "gpiozero": SimpleNamespace(DigitalInputDevice=self.creer_rng),
            "gpiozero.pins": SimpleNamespace(),
            "gpiozero.pins.lgpio": SimpleNamespace(LGPIOFactory=self.creer_fabrique),
        }
        ressources.enter_context(patch.dict(sys.modules, modules))
        ressources.enter_context(patch.object(rfid.time, "monotonic", lambda: self.maintenant))

    def lire(self, lecteur, instant, presente=None, donnees=b""):
        self.maintenant = instant
        if presente is not None:
            self.rng.definir(presente)
        self.uart.tampon.extend(donnees)
        return lecteur.lire()


def lectures(evenements):
    return [e for e in evenements if e.type in ("ACCEPTE", "IGNORE", "INVALIDE")]


class TestsAcquisition(unittest.TestCase):
    def setUp(self):
        self.ressources = ExitStack()
        self.addCleanup(self.ressources.close)
        self.banc = BancSimule()
        self.banc.installer(self.ressources)

    def ouvrir(self):
        lecteur = self.ressources.enter_context(rfid.LecteurRFID())
        lecteur.lire()  # Consommer les messages de demarrage.
        return lecteur

    def test_configuration_du_montage_et_lecture_non_bloquante(self):
        lecteur = self.ouvrir()
        self.assertEqual(self.banc.chips, [0])
        self.assertEqual((self.banc.port, self.banc.gpio), ("/dev/ttyAMA0", 17))
        self.assertEqual(self.banc.options_uart, dict(
            baudrate=9600, bytesize=8, parity="N", stopbits=1, timeout=0,
            xonxoff=False, rtscts=False, dsrdtr=False, exclusive=True,
        ))
        self.assertIsNone(self.banc.options_gpio["pull_up"])
        self.assertTrue(self.banc.options_gpio["active_state"])
        with patch.object(rfid.time, "sleep", side_effect=AssertionError("attente interdite")):
            self.assertEqual(lecteur.lire(), [])
        self.banc.lire(lecteur, 1, donnees=b"x" * 600)
        self.assertEqual(self.banc.tailles_lues[-1], 256)

    def test_une_decision_par_identifiant_et_presentation(self):
        lecteur = self.ouvrir()
        evts = lectures(self.banc.lire(lecteur, 1, True, BADGE_A + BADGE_A))
        self.assertEqual([e.type for e in evts], ["ACCEPTE", "IGNORE"])
        self.assertEqual(evts[0].identifiant, "1100823734")

    def test_absence_rng_interdit_la_lecture(self):
        lecteur = self.ouvrir()
        evts = lectures(self.banc.lire(lecteur, 1, donnees=BADGE_A))
        self.assertEqual([e.type for e in evts], ["IGNORE"])

    def test_retrait_puis_rearmement_a_500_ms(self):
        lecteur = self.ouvrir()
        self.banc.lire(lecteur, 1, True, BADGE_A)
        self.banc.lire(lecteur, 2, False)
        evts = lectures(self.banc.lire(lecteur, 2.5, True, BADGE_A))
        self.assertEqual([e.type for e in evts], ["ACCEPTE"])

    def test_badge_trop_rapide_reste_ignore_meme_apres_le_delai(self):
        lecteur = self.ouvrir()
        self.banc.lire(lecteur, 1, True, BADGE_A)
        self.banc.lire(lecteur, 2, False)
        evts = lectures(self.banc.lire(lecteur, 2.1, True, BADGE_A))
        self.assertEqual([e.type for e in evts], ["IGNORE"])
        self.assertEqual(self.banc.lire(lecteur, 3), [])
        evts = lectures(self.banc.lire(lecteur, 4, donnees=BADGE_A))
        self.assertEqual([e.type for e in evts], ["IGNORE"])
        self.banc.lire(lecteur, 5, False)
        evts = lectures(self.banc.lire(lecteur, 5.5, True, BADGE_A))
        self.assertEqual([e.type for e in evts], ["ACCEPTE"])

    def test_badge_different_accepte_pendant_delai_du_precedent(self):
        lecteur = self.ouvrir()
        self.banc.lire(lecteur, 1, True, BADGE_A)
        self.banc.lire(lecteur, 2, False)
        evts = lectures(self.banc.lire(lecteur, 2.1, True, BADGE_B))
        self.assertEqual([e.type for e in evts], ["ACCEPTE"])
        self.assertEqual(evts[0].identifiant, "11008827F9")

    def test_arrivee_rng_trop_tot_reste_refusee_si_uart_termine_plus_tard(self):
        lecteur = self.ouvrir()
        self.banc.lire(lecteur, 1, True, BADGE_A)
        self.banc.lire(lecteur, 2, False)
        self.banc.lire(lecteur, 2.49, True, BADGE_A[:4])
        evts = lectures(self.banc.lire(lecteur, 2.51, donnees=BADGE_A[4:]))
        self.assertEqual([e.type for e in evts], ["IGNORE"])

    def test_trame_fractionnee_et_retrait_avant_dernier_octet(self):
        lecteur = self.ouvrir()
        self.banc.lire(lecteur, 1, True, BADGE_A[:8])
        evts = lectures(self.banc.lire(lecteur, 1.01, False, BADGE_A[8:]))
        self.assertEqual([e.type for e in evts], ["ACCEPTE"])
        evts = lectures(self.banc.lire(lecteur, 1.1, True, BADGE_A))
        self.assertEqual([e.type for e in evts], ["IGNORE"])

    def test_trame_incomplete_expire_pendant_silence_uart(self):
        lecteur = self.ouvrir()
        self.banc.lire(lecteur, 1, True, BADGE_A[:7])
        evts = lectures(self.banc.lire(lecteur, 1.25))
        self.assertEqual([e.type for e in evts], ["INVALIDE"])
        self.assertIn("delai depasse", evts[0].message)

    def test_checksum_invalide_natteint_pas_la_borne(self):
        lecteur = self.ouvrir()
        mauvaise = b"\x02110082373400\r\n\x03"
        evts = lectures(self.banc.lire(lecteur, 1, True, mauvaise + BADGE_A))
        self.assertEqual([e.type for e in evts], ["INVALIDE", "ACCEPTE"])

    def test_resynchronisation_apres_bruit_et_nouveau_stx(self):
        lecteur = self.ouvrir()
        evts = lectures(self.banc.lire(lecteur, 1, True, b"bruit\x0211" + BADGE_A))
        self.assertEqual([e.type for e in evts], ["INVALIDE", "ACCEPTE"])

    def test_badge_present_au_demarrage_exige_un_retrait(self):
        self.banc.initial = True
        lecteur = self.ouvrir()
        evts = lectures(self.banc.lire(lecteur, 1, donnees=BADGE_A))
        self.assertEqual([e.type for e in evts], ["IGNORE"])
        self.assertIn("demarrage", evts[0].message)
        self.banc.lire(lecteur, 2, False)
        evts = lectures(self.banc.lire(lecteur, 2.1, True, BADGE_A))
        self.assertEqual([e.type for e in evts], ["ACCEPTE"])

    def test_trame_du_demarrage_reste_ignoree_si_retrait_pendant_reception(self):
        self.banc.initial = True
        lecteur = self.ouvrir()
        self.banc.lire(lecteur, 1, donnees=BADGE_A[:8])
        evts = lectures(self.banc.lire(lecteur, 1.01, False, BADGE_A[8:]))
        self.assertEqual([e.type for e in evts], ["IGNORE"])

    def test_fermeture_de_toutes_les_ressources_et_idempotence(self):
        lecteur = self.ouvrir()
        lecteur.ouvrir()
        lecteur.fermer()
        lecteur.fermer()
        self.assertEqual(self.banc.chips, [0])
        self.assertEqual(self.banc.fermetures, ["uart", "rng", "fabrique"])
        with self.assertRaisesRegex(RuntimeError, "non ouvert"):
            lecteur.lire()

    def test_echec_ouverture_uart_libere_gpio(self):
        self.banc.erreur_ouverture = True
        with self.assertRaises(OSError):
            self.ouvrir()
        self.assertEqual(self.banc.fermetures, ["rng", "fabrique"])

    def test_echec_vidage_uart_libere_toutes_les_ressources(self):
        self.banc.erreur_vidage = True
        with self.assertRaises(OSError):
            self.ouvrir()
        self.assertEqual(self.banc.fermetures, ["uart", "rng", "fabrique"])

    def test_erreur_de_lecture_libere_toutes_les_ressources(self):
        with self.assertRaises(OSError):
            with rfid.LecteurRFID() as lecteur:
                self.banc.erreur_lecture = True
                lecteur.lire()
        self.assertEqual(self.banc.fermetures, ["uart", "rng", "fabrique"])

    def test_reouverture_isole_les_anciens_callbacks(self):
        lecteur = self.ouvrir()
        ancien_callback = self.banc.rng.when_activated
        lecteur.fermer()
        lecteur.ouvrir()
        lecteur.lire()
        ancien_callback()
        evts = lectures(self.banc.lire(lecteur, 1, donnees=BADGE_A))
        self.assertEqual([e.type for e in evts], ["IGNORE"])


class TestsFormatEtOptions(unittest.TestCase):
    def test_trois_badges_releves_sur_le_pi(self):
        for trame, identifiant in ((BADGE_A, "1100823734"),
                                   (BADGE_B, "11008827F9"), (BADGE_C, "1100880F2D")):
            with self.subTest(identifiant=identifiant):
                self.assertEqual(rfid.verifier_trame(trame), identifiant)

    def test_delimiteurs_et_caracteres_invalides(self):
        for trame in (BADGE_A[:-1], b"\x00" + BADGE_A[1:],
                      BADGE_A[:-3] + b"\n\r\x03", b"\x02Z10082373490\r\n\x03"):
            with self.subTest(trame=trame):
                with self.assertRaises(ValueError):
                    rfid.verifier_trame(trame)

    def test_options_par_defaut_correspondent_au_montage(self):
        args = rfid.lire_arguments([])
        self.assertEqual((args.port, args.gpio, args.chip, args.delai_ms),
                         ("/dev/ttyAMA0", 17, 0, 500))

    def test_parametres_invalides_rejetes_avant_acces_materiel(self):
        for options in ({"delai_ms": -1}, {"delai_ms": float("nan")},
                        {"delai_ms": float("inf")}, {"chip": -1}, {"gpio": -1}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    rfid.LecteurRFID(**options)

    def test_import_des_deux_modules_sans_bibliotheques_materielles(self):
        code = '''import sys
sys.modules.update(serial=None, gpiozero=None, lgpio=None)
sys.path.insert(0, sys.argv[1])
from modules import lecteur_nfc_rfid
import main
lecteur_nfc_rfid.LecteurRFID()
'''
        resultat = subprocess.run([sys.executable, "-c", code, str(RPI)], capture_output=True, text=True)
        self.assertEqual(resultat.returncode, 0, resultat.stderr)


class TestsProgrammePrincipal(unittest.TestCase):
    def test_main_transmet_seulement_les_lectures_acceptees_et_libere_le_lecteur(self):
        evenements = [rfid.EvenementRFID("ACCEPTE", "valide", "1100823734"),
                      rfid.EvenementRFID("IGNORE", "trop vite", "1100823734"),
                      rfid.EvenementRFID("INVALIDE", "checksum")]
        with patch.object(rfid, "LecteurRFID") as classe, \
             patch.object(borne, "traiter_badge") as traiter, \
             patch.object(borne.time, "sleep", side_effect=KeyboardInterrupt), \
             redirect_stdout(io.StringIO()):
            classe.return_value.__enter__.return_value.lire.return_value = evenements
            self.assertEqual(borne.main([]), 0)
            traiter.assert_called_once_with("1100823734")
            classe.return_value.__exit__.assert_called_once()
            classe.assert_called_once_with(port="/dev/ttyAMA0", gpio=17, chip=0, delai_ms=500)

    def test_erreur_materielle_signalee_avec_code_echec(self):
        erreur = io.StringIO()
        with patch.object(rfid, "LecteurRFID") as classe, redirect_stderr(erreur):
            classe.return_value.__enter__.side_effect = OSError("UART inaccessible")
            self.assertEqual(borne.main([]), 1)
        self.assertIn("UART inaccessible", erreur.getvalue())


if __name__ == "__main__":
    unittest.main()
