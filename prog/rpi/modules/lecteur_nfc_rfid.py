#!/usr/bin/env python3
"""Test ESA : ID-12LA sur UART0 + RNG sur GPIO17 (CM5 / Pi 5).

Lancement sur le Pi : sudo python3 test_rfid.py
Delai modifiable :    sudo python3 test_rfid.py --delai-ms 1000

Ce programme affiche des decisions de lecture. Il ne modifie aucun compte
et ne commande aucun actionneur. Une lecture refusee n'est jamais rejouee
automatiquement : retirer puis representer le badge.

Sources : fiche ID Innovations ID-2/12/20 LA, sections 4 et 6 ;
https://gpiozero.readthedocs.io/en/stable/api_input.html
https://gpiozero.readthedocs.io/en/stable/api_pins.html
https://pyserial.readthedocs.io/en/latest/pyserial_api.html

Le delai de 500 ms est notre choix d'essai, pas une exigence du lecteur.
"""

import argparse
from contextlib import ExitStack
from dataclasses import dataclass, field
from math import ceil, isfinite
from pathlib import Path
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


def trouver_rp1(racine=Path("/dev"), api=None):
    """Identifier RP1 via l'API gpiochip, sans dependre des attributs sysfs."""
    if api is None:
        import lgpio as api

    correspondances = []
    diagnostics = []
    for chemin in sorted(racine.glob("gpiochip*")):
        suffixe = chemin.name.removeprefix("gpiochip")
        if not suffixe.isdecimal():
            continue
        numero = int(suffixe)
        handle = None
        try:
            handle = api.gpiochip_open(numero)
            if handle < 0:
                raise RuntimeError(f"ouverture impossible (code {handle})")
            infos = api.gpio_get_chip_info(handle)
            # Le nom Linux et le libelle fonctionnel sont les deux derniers
            # champs ; les champs numeriques precedents varient selon l'API.
            nom, etiquette = infos[-2:]
            if isinstance(etiquette, bytes):
                etiquette = etiquette.decode("utf-8", errors="replace")
            diagnostics.append(f"{chemin.name} : {nom!r}, {etiquette!r}")
            if "rp1" in str(etiquette).lower():
                correspondances.append(numero)
        except Exception as erreur:
            diagnostics.append(f"{chemin.name} : {type(erreur).__name__}: {erreur}")
        finally:
            if handle is not None and handle >= 0:
                api.gpiochip_close(handle)
    if len(correspondances) != 1:
        raise RuntimeError(
            "Controleur GPIO RP1 non identifie de facon unique. "
            "Informations lues : " + (" ; ".join(diagnostics) or "aucun /dev/gpiochip*")
        )
    return correspondances[0]


def executer(args):
    # Imports tardifs : les fonctions de validation peuvent etre testees sans Pi.
    import serial
    from gpiozero import DigitalInputDevice
    from gpiozero.pins.lgpio import LGPIOFactory

    origine = time.monotonic()

    def afficher(message):
        print(f"[{time.monotonic() - origine:8.3f} s] {message}", flush=True)

    transitions = SimpleQueue()
    regle = Rearmement(args.delai_ms / 1000)
    reception = Reception()
    chip = args.chip if args.chip is not None else trouver_rp1()

    with ExitStack() as ressources:
        fabrique = LGPIOFactory(chip=chip)
        ressources.callback(fabrique.close)
        rng = DigitalInputDevice(
            args.gpio, pull_up=None, active_state=True,
            bounce_time=None, pin_factory=fabrique,
        )
        ressources.callback(rng.close)
        uart = serial.Serial(
            args.port, baudrate=9600, bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
            timeout=0, xonxoff=False, rtscts=False, dsrdtr=False,
            exclusive=True,
        )
        ressources.callback(uart.close)
        uart.reset_input_buffer()

        # Les callbacks ne font qu'enregistrer les fronts. Le traitement est
        # effectue dans la boucle principale, sans acces concurrent aux etats.
        rng.when_activated = lambda: transitions.put((True, time.monotonic()))
        rng.when_deactivated = lambda: transitions.put((False, time.monotonic()))
        initial = rng.is_active
        regle.presence(initial, time.monotonic())
        afficher(f"{args.port} : 9600 8N1 | RNG=GPIO{args.gpio} | gpiochip{chip}")
        afficher(f"Delai du meme badge : {args.delai_ms:g} ms apres retrait")
        afficher("ACCEPTE = lecture valide, pas une autorisation de compte.")
        if initial:
            afficher("Un badge est deja present : retirez-le puis representez-le.")
        else:
            afficher("Presentez un badge. Ctrl+C pour terminer.")

        while True:
            while True:
                try:
                    presente, instant = transitions.get_nowait()
                except Empty:
                    break
                message = regle.presence(presente, instant)
                if message:
                    afficher(message)

            # Taille bornee, lecture non bloquante et horloge monotone :
            # les 500 ms n'immobilisent jamais le programme.
            donnees = uart.read(min(uart.in_waiting, 256))
            maintenant = time.monotonic()
            for evenement in reception.recevoir(donnees, maintenant, regle.presentation):
                if evenement[0] == "erreur":
                    afficher(f"INVALIDE : {evenement[1]} | {evenement[2].hex(' ')}")
                    continue
                _, trame, debut, presentation = evenement
                try:
                    identifiant = verifier_trame(trame)
                except ValueError as erreur:
                    afficher(f"INVALIDE : {erreur} | {trame.hex(' ')}")
                    continue
                decision, raison = regle.decider(identifiant, presentation, debut)
                afficher(f"{decision} | ID={identifiant} | {raison}")
            time.sleep(0.002)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", default="/dev/ttyAMA0", help="port UART (defaut : /dev/ttyAMA0)")
    parser.add_argument("--gpio", type=int, default=17, help="numero BCM de RNG (defaut : 17)")
    parser.add_argument("--delai-ms", type=float, default=500, help="delai apres retrait pour le meme ID")
    parser.add_argument("--chip", type=int, help="numero gpiochip ; detection automatique RP1 sinon")
    args = parser.parse_args()
    if not isfinite(args.delai_ms) or args.delai_ms < 0:
        parser.error("--delai-ms doit etre un nombre positif ou nul")
    if args.chip is not None and args.chip < 0:
        parser.error("--chip doit etre positif ou nul")
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
