#!/usr/bin/env python3
"""Lecteur RFID ID-12LA : UART0 + RNG sur GPIO17 (CM5 / Pi 5).

Depuis le projet : sudo python3 prog/rpi/main.py
Test direct : sudo python3 prog/rpi/modules/lecteur_nfc_rfid.py
Options : --port /dev/ttyAMA0 --gpio 17 --chip 0 --delai-ms 500

LecteurRFID s'ouvre avec un bloc ``with`` ; lire() rend les evenements
disponibles sans attendre une trame ni la fin du delai de rearmement.
Seul le programme principal decide quoi faire d'un identifiant accepte.
ACCEPTE signifie lecture valide, pas autorisation de compte.

Le delai de 500 ms concerne le meme identifiant apres son retrait.
Une presentation refusee n'est jamais rejouee automatiquement.

Sources : fiche ID Innovations ID-2/12/20 LA, sections 4 et 6 ;
https://gpiozero.readthedocs.io/en/stable/api_input.html
https://gpiozero.readthedocs.io/en/stable/api_pins.html
https://pyserial.readthedocs.io/en/latest/pyserial_api.html
"""

import argparse
from contextlib import ExitStack
from dataclasses import dataclass, field
from math import ceil, isfinite
from queue import Empty, SimpleQueue
import re
import sys
import time


@dataclass
class Presentation:
    arrivee: float
    retrait: float | None = None
    identifiants: set[str] = field(default_factory=set)


class Rearmement:
    """Une decision par ID/presentation ; temporisation apres le retrait."""

    def __init__(self, delai=0.5):
        self.delai = delai
        self.presentation = None
        self.derniers_retraits = {}

    def presence(self, presente, maintenant):
        if presente and self.presentation is None:
            self.presentation = Presentation(maintenant)
            return "RNG=1 : badge dans la zone"
        if not presente and self.presentation is not None:
            self.presentation.retrait = maintenant
            for identifiant in self.presentation.identifiants:
                self.derniers_retraits[identifiant] = maintenant
            self.presentation = None
            return "RNG=0 : retrait detecte"
        return None

    def decider(self, identifiant, presentation, debut_trame):
        if presentation is None:
            return "IGNORE", "RNG absent au debut de la trame ; representer le badge"
        if identifiant in presentation.identifiants:
            return "IGNORE", "identifiant deja traite pendant cette presentation"

        # Premiere lecture : utiliser l'arrivee RNG, meme si l'UART termine
        # sa trame apres expiration du delai. Si un autre ID apparait sans
        # front RNG intermediaire, utiliser le debut de sa propre trame.
        arrivee = presentation.arrivee if not presentation.identifiants else debut_trame
        dernier_retrait = self.derniers_retraits.get(identifiant)
        presentation.identifiants.add(identifiant)

        # Le retrait peut arriver pendant la reception des 16 octets.
        # La reference a la presentation conserve alors ce retrait.
        if presentation.retrait is not None:
            self.derniers_retraits[identifiant] = presentation.retrait

        if dernier_retrait is not None:
            restant = self.delai - (arrivee - dernier_retrait)
            if restant > 1e-9:
                return "IGNORE", (
                    f"meme badge represente trop vite ({ceil(restant * 1000)} ms restantes) ; "
                    "retirer puis representer"
                )
        return "ACCEPTE", "trame et checksum valides"


def verifier_trame(trame):
    """STX + 10 caracteres ID + 2 checksum + CR LF ETX = 16 octets."""
    if len(trame) != 16 or trame[:1] != b"\x02" or trame[-3:] != b"\r\n\x03":
        raise ValueError("longueur ou delimiteurs incorrects")
    if re.fullmatch(rb"[0-9A-Fa-f]{12}", trame[1:13]) is None:
        raise ValueError("caracteres non hexadecimaux")
    identifiant = trame[1:11].decode("ascii").upper()
    calcule = 0
    for octet in bytes.fromhex(identifiant):
        calcule ^= octet
    recu = int(trame[11:13], 16)
    if calcule != recu:
        raise ValueError(f"checksum recu {recu:02X}, attendu {calcule:02X}")
    return identifiant


class Reception:
    """Reception progressive : pas d'attente bloquante de fin de trame."""

    def __init__(self, duree_max=0.25):
        self.duree_max = duree_max
        self.tampon = bytearray()
        self.debut = 0.0
        self.presentation = None

    def expirer(self, maintenant):
        if self.tampon and maintenant - self.debut >= self.duree_max:
            brut = bytes(self.tampon)
            self.tampon.clear()
            self.presentation = None
            return ("erreur", "trame incomplete : delai depasse", brut)
        return None

    def recevoir(self, donnees, maintenant, presentation):
        resultats = []
        expiration = self.expirer(maintenant)
        if expiration:
            resultats.append(expiration)
        for octet in donnees:
            if octet == 0x02:
                if self.tampon:
                    resultats.append(("erreur", "nouveau STX avant la fin", bytes(self.tampon)))
                self.tampon = bytearray([octet])
                self.debut = maintenant
                self.presentation = presentation
            elif self.tampon:
                self.tampon.append(octet)
                if octet == 0x03 or len(self.tampon) == 16:
                    resultats.append(("trame", bytes(self.tampon), self.debut, self.presentation))
                    self.tampon.clear()
                    self.presentation = None
            # Les octets hors trame sont ignores jusqu'au prochain STX.
        return resultats


@dataclass(frozen=True)
class EvenementRFID:
    """INFO, PRESENCE, RETRAIT, ACCEPTE, IGNORE ou INVALIDE."""

    type: str
    message: str
    identifiant: str | None = None
    brut: bytes = b""

    def __str__(self):
        if self.type in ("INFO", "PRESENCE", "RETRAIT"):
            return self.message
        if self.identifiant is not None:
            return f"{self.type} | ID={self.identifiant} | {self.message}"
        detail = f" | {self.brut.hex(' ')}" if self.brut else ""
        return f"{self.type} : {self.message}{detail}"


class LecteurRFID:
    """Acquisition appelee depuis une seule boucle applicative.

    Construire l'objet n'ouvre pas le materiel. Utiliser ``with`` ou appeler
    ouvrir(), puis lire() regulierement et fermer() en fin d'utilisation.
    Les callbacks GPIO deposent uniquement les fronts dans une file.
    """

    def __init__(self, port="/dev/ttyAMA0", gpio=17, chip=0, delai_ms=500):
        if not isfinite(delai_ms) or delai_ms < 0:
            raise ValueError("delai_ms doit etre un nombre positif ou nul")
        if not isinstance(chip, int) or chip < 0:
            raise ValueError("chip doit etre un entier positif ou nul")
        if not isinstance(gpio, int) or gpio < 0:
            raise ValueError("gpio doit etre un numero BCM positif ou nul")
        self.port = port
        self.gpio = gpio
        self.chip = chip
        self.delai_ms = delai_ms
        self._ressources = None
        self._uart = None
        self._rng = None

    def ouvrir(self):
        if self._ressources is not None:
            return self

        # Imports tardifs : importation du module et tests possibles sur PC.
        import serial
        from gpiozero import DigitalInputDevice
        from gpiozero.pins.lgpio import LGPIOFactory

        transitions = SimpleQueue()
        self._transitions = transitions
        self._regle = Rearmement(self.delai_ms / 1000)
        self._reception = Reception()
        self._evenements = []

        # Toute ouverture partielle est liberee si une etape echoue.
        with ExitStack() as ressources:
            fabrique = LGPIOFactory(chip=self.chip)
            ressources.callback(fabrique.close)
            rng = DigitalInputDevice(
                self.gpio, pull_up=None, active_state=True,
                bounce_time=None, pin_factory=fabrique,
            )
            ressources.callback(rng.close)
            uart = serial.Serial(
                self.port, baudrate=9600, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                timeout=0, xonxoff=False, rtscts=False, dsrdtr=False,
                exclusive=True,
            )
            ressources.callback(uart.close)
            uart.reset_input_buffer()

            rng.when_activated = lambda: transitions.put((True, time.monotonic()))
            rng.when_deactivated = lambda: transitions.put((False, time.monotonic()))
            initial = rng.is_active
            self._regle.presence(initial, time.monotonic())
            # Le test demandait deja un retrait au demarrage. Le module
            # l'impose aussi si des octets arrivent pendant ce demarrage.
            self._presentation_initiale = self._regle.presentation if initial else None
            self._evenements = [
                EvenementRFID("INFO", f"{self.port} : 9600 8N1 | RNG=GPIO{self.gpio} | gpiochip{self.chip}"),
                EvenementRFID("INFO", f"Delai du meme badge : {self.delai_ms:g} ms apres retrait"),
                EvenementRFID("INFO", "ACCEPTE = lecture valide, pas une autorisation de compte."),
                EvenementRFID("INFO", "Un badge est deja present : retirez-le puis representez-le."
                              if initial else "Presentez un badge. Ctrl+C pour terminer."),
            ]
            self._uart = uart
            self._rng = rng
            self._ressources = ressources.pop_all()
        return self

    def lire(self):
        """Retourne les evenements disponibles ; aucune attente de 500 ms.

        Lire au plus 256 octets par passage. Le programme appelant doit
        revenir regulierement (toutes les 2 ms dans main.py) et eviter de
        bloquer sa boucle pendant les futurs traitements CAN/MQTT/ecran.
        """
        if self._ressources is None:
            raise RuntimeError("Lecteur RFID non ouvert")

        evenements, self._evenements = self._evenements, []
        while True:
            try:
                presente, instant = self._transitions.get_nowait()
            except Empty:
                break
            message = self._regle.presence(presente, instant)
            if message:
                evenements.append(EvenementRFID("PRESENCE" if presente else "RETRAIT", message))

        donnees = self._uart.read(min(self._uart.in_waiting, 256))
        maintenant = time.monotonic()
        presentation = self._regle.presentation
        for resultat in self._reception.recevoir(donnees, maintenant, presentation):
            if resultat[0] == "erreur":
                evenements.append(EvenementRFID("INVALIDE", resultat[1], brut=resultat[2]))
                continue
            _, trame, debut, presentation = resultat
            try:
                identifiant = verifier_trame(trame)
            except ValueError as erreur:
                evenements.append(EvenementRFID("INVALIDE", str(erreur), brut=trame))
                continue
            if presentation is not None and presentation is self._presentation_initiale:
                evenements.append(EvenementRFID(
                    "IGNORE", "badge deja present au demarrage ; retirer puis representer", identifiant,
                ))
                continue
            decision, raison = self._regle.decider(identifiant, presentation, debut)
            evenements.append(EvenementRFID(decision, raison, identifiant))
        return evenements

    def fermer(self):
        ressources, self._ressources = self._ressources, None
        try:
            if ressources is not None:
                ressources.close()
        finally:
            self._uart = None
            self._rng = None

    def __enter__(self):
        return self.ouvrir()

    def __exit__(self, exc_type, exc_value, traceback):
        self.fermer()
        return False


def lire_arguments(argv=None, description=None):
    """Options communes au programme principal et au test direct."""
    parser = argparse.ArgumentParser(description=description or __doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", default="/dev/ttyAMA0", help="port UART (defaut : /dev/ttyAMA0)")
    parser.add_argument("--gpio", type=int, default=17, help="numero BCM de RNG (defaut : 17)")
    parser.add_argument("--delai-ms", type=float, default=500, help="delai apres retrait pour le meme ID")
    parser.add_argument("--chip", type=int, default=0, help="numero gpiochip (defaut : 0, identifie sur ce CM5)")
    args = parser.parse_args(argv)
    if not isfinite(args.delai_ms) or args.delai_ms < 0:
        parser.error("--delai-ms doit etre un nombre positif ou nul")
    if args.chip < 0:
        parser.error("--chip doit etre positif ou nul")
    if args.gpio < 0:
        parser.error("--gpio doit etre positif ou nul")
    return args


def executer(args):
    """Boucle du test direct ; main.py utilise LecteurRFID.lire()."""
    origine = time.monotonic()
    with LecteurRFID(port=args.port, gpio=args.gpio, chip=args.chip,
                     delai_ms=args.delai_ms) as lecteur:
        while True:
            for evenement in lecteur.lire():
                print(f"[{time.monotonic() - origine:8.3f} s] {evenement}", flush=True)
            time.sleep(0.002)


def main(argv=None):
    args = lire_arguments(argv)
    try:
        executer(args)
    except KeyboardInterrupt:
        print("\nTest termine.")
        return 0
    except Exception as erreur:
        print(f"ERREUR {type(erreur).__name__} : {erreur}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
