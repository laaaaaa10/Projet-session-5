"""Banc T12 avec le vrai t06_ir.c du BAS compilé sur Linux.

Seules ses deux interfaces PCB-04 sont simulées. Le HAUT, les moteurs,
T04, la sécurité et le transport restent les doubles explicites du banc.
Aucun SocketCAN, GPIO ou firmware matériel n'est ouvert/flashé.
"""
import ctypes as C
from pathlib import Path
import shutil
import subprocess

from exemples.banc_retrait import BusRetraitSimule

SOURCE_T06 = Path(__file__).resolve().parents[2] / 'stm32_bas/Core/Src/t06_ir.c'


def compiler_t06(dossier):
    """Une image distincte par banc : le module C possède des variables globales."""
    compilateur = shutil.which('cc') or shutil.which('gcc')
    if compilateur is None:
        raise RuntimeError('Compilateur C absent : installer build-essential sur le PC Linux.')
    sortie = Path(dossier) / 't06_bas.so'
    subprocess.run([compilateur, '-std=c99', '-Wall', '-Wextra', '-Werror', '-O2',
                    '-shared', '-fPIC', '-DT06_PRESENCE_SI_PORTEUSE=0',
                    '-I', str(SOURCE_T06.parent.parent / 'Inc'),
                    str(SOURCE_T06), '-o', str(sortie)], check=True)
    return sortie


_Choisir = C.CFUNCTYPE(C.c_bool, C.c_void_p, C.c_int8)
_Lire = C.CFUNCTYPE(C.c_bool, C.c_void_p, C.POINTER(C.c_uint8))
_Envoyer = C.CFUNCTYPE(C.c_bool, C.c_uint16, C.POINTER(C.c_uint8), C.c_uint8)


class _Carte(C.Structure):
    _fields_ = [('choisir_emetteur', _Choisir), ('lire_recepteurs', _Lire), ('ctx', C.c_void_p)]


class CodeT06:
    """ABI directe de t06_ir.h ; les octets CAN viennent exclusivement du C.

    Le banc tourne deux appels T06_Tache par ms simulée, comme test_t06_ir.c.
    Les callbacks et le tableau des cartes restent vivants aussi longtemps
    que la bibliothèque. Une bibliothèque compilée ne sert qu'à un banc.
    """
    def __init__(self, bibliotheque, maintenant_ms, *, nb_cartes=2):
        self.lib = C.CDLL(str(Path(bibliotheque).resolve()))
        self.maintenant_ms = maintenant_ms
        self.trames = []
        self.emetteurs = [-1, -1]
        self.vehicules = [[False] * 8 for _ in range(2)]
        self.parasites = [[False] * 8 for _ in range(2)]
        self.erreurs = [False, False]
        self.indices = (C.c_uint8 * 8 * 2).in_dll(self.lib, 'T06_INDICE')
        self.recepteurs = (C.c_uint8 * 8 * 2).in_dll(self.lib, 'T06_RECEPTEUR')
        self._choisir = _Choisir(self._choix)
        self._lire = _Lire(self._lecture)
        self._envoyer = _Envoyer(self._envoi)
        self._cartes = (_Carte * 2)(*[_Carte(self._choisir, self._lire, i) for i in range(2)])
        self.lib.T06_Init.argtypes = [C.POINTER(_Carte), C.c_uint8, _Envoyer, C.c_uint32]
        self.lib.T06_Init.restype = C.c_bool
        self.lib.T06_Tache.argtypes, self.lib.T06_Tache.restype = [C.c_uint32], None
        self.lib.T06_TraiterTrame.argtypes = [C.c_uint16, C.c_uint8, C.POINTER(C.c_uint8)]
        self.lib.T06_TraiterTrame.restype = None
        if not self.lib.T06_Init(self._cartes, nb_cartes, self._envoyer, maintenant_ms):
            raise RuntimeError('T06_Init a refusé le banc')

    def _choix(self, ctx, circuit):
        carte = ctx or 0
        if self.erreurs[carte]:
            return False
        self.emetteurs[carte] = circuit
        return True

    def _lecture(self, ctx, niveaux):
        carte = ctx or 0
        if self.erreurs[carte]:
            return False
        valeur = 0xFF
        for recepteur in range(8):
            porteuse = self.parasites[carte][recepteur]
            circuit = self.emetteurs[carte]
            if circuit >= 0 and self.recepteurs[carte][circuit] == recepteur:
                porteuse |= not self.vehicules[carte][circuit]  # faisceau coupé = présence
            if porteuse:
                valeur &= ~(1 << recepteur)
        niveaux[0] = valeur
        return True

    def _envoi(self, ident, donnees, dlc):
        # Pas de rappel T12 depuis ctypes : aucune exception Python n'est avalée
        # par une frontière C. Le bus livre ensuite les trames dans leur ordre.
        self.trames.append((self.maintenant_ms, ident, bytes(donnees[:dlc])))
        return True

    def avancer(self, maintenant_ms):
        while self.maintenant_ms < maintenant_ms:
            self.lib.T06_Tache(self.maintenant_ms)
            self.lib.T06_Tache(self.maintenant_ms)
            self.maintenant_ms += 1

    def recevoir(self, ident, donnees):
        d = (C.c_uint8 * len(donnees))(*donnees)
        self.lib.T06_TraiterTrame(ident, len(donnees), d)

    def changer_place(self, place, present):
        for carte in range(2):
            for circuit in range(8):
                if self.indices[carte][circuit] == place - 1:
                    self.vehicules[carte][circuit] = present
                    return
        raise ValueError('Place absente de la table C')


class BusRetraitCodeT06(BusRetraitSimule):
    """Bus en mémoire : BAS compilé ; HAUT et actionneurs simulés."""
    def __init__(self, horloge, *, bibliotheque, nb_cartes=2, valider_demarrage=True):
        super().__init__(horloge)
        self.repondre_lecture_ir = False  # interdit les 0x301 fabriqués par le banc d'origine
        self.haut_actif = True
        self.trace_bas = []
        self.t06 = CodeT06(bibliotheque, round(horloge() * 1000), nb_cartes=nb_cartes)
        for place, present in self.places.items():
            self.t06.changer_place(place, present)
        if valider_demarrage:
            horloge.temps += .25
            self._balayer()

    def _publier_bas(self):
        trames, self.t06.trames = self.t06.trames, []
        for date, ident, donnees in trames:
            self.trace_bas.append((date, ident, donnees))
            self.emettre(ident, donnees)

    def _balayer(self):
        self.t06.avancer(round(self.horloge() * 1000))
        self._publier_bas()

    def surveillance(self):
        self._balayer()
        super().surveillance()  # heartbeats toujours simulés, y compris celui du BAS

    def envoyer(self, ident, donnees):
        super().envoyer(ident, donnees)
        if ident in (0x302, 0x080):
            self.t06.recevoir(ident, donnees)
            self._publier_bas()
            if self.haut_actif and ident == 0x302 and bytes(donnees) in (b'\x02', b'\xff'):
                self.emettre(0x311, [int(self.rampe), self.compteur_sortie, 1])

    def synchroniser_ir(self):
        self.t06.recevoir(0x302, [1])
        self._publier_bas()
        if self.haut_actif:
            self.emettre(0x311, [int(self.rampe), self.compteur_sortie, 1])

    def ir_place(self, place, present):
        self.places[place] = present
        self.t06.changer_place(place, present)  # aucune trame avant le filtrage C

    def ir_sortie(self, present):
        if self.haut_actif:
            super().ir_sortie(present)
