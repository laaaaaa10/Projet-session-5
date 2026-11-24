"""
lecteur_code_barres.py - T05 (RPi) : lecture du numéro de billet au retrait.

Le lecteur MJ-2090-CCD se présente comme un CLAVIER USB : il « tape » les
chiffres du code-barres puis Entrée. Pour que ces frappes n'arrivent pas
ailleurs dans l'interface, le lecteur est lu directement avec evdev et
« réservé » (grab) : seul ce module reçoit ses frappes.

Lecture par codes de touches (KEY_0 à KEY_9) : le résultat ne dépend pas
de la disposition du clavier (fr-CA, en-US...).

  - traiter_saisie(texte)  valide le FORMAT (6 chiffres) ; sert aussi à la
                           saisie manuelle. L'existence de la transaction
                           est vérifiée par T04, pas ici.
  - demarrer()             lance la lecture du lecteur USB dans un fil séparé
  - est_disponible()       indique si le lecteur est branché

Projet ESA - 243-557 - Automne 2026
"""
import re
import threading

try:
    import evdev
    from evdev import ecodes
except ImportError:          # permet d'utiliser traiter_saisie() sans evdev (PC)
    evdev = None
    ecodes = None

LONGUEUR_NUMERO = 6
LONGUEUR_MAX_TAMPON = 32          # protection contre une lecture anormale

# Mots recherchés dans le nom du périphérique si aucun nom n'est fourni
NOMS_PAR_DEFAUT = ("barcode", "scanner", "bar code")


def _codes_chiffres():
    """Associe les codes de touches (rangée du haut et pavé numérique) aux chiffres."""
    if ecodes is None:
        return {}
    table = {}
    for chiffre in range(10):
        table[getattr(ecodes, f"KEY_{chiffre}")] = str(chiffre)
        table[getattr(ecodes, f"KEY_KP{chiffre}")] = str(chiffre)
    return table


class LecteurCodeBarres:
    """Lecteur de codes-barres USB (mode clavier HID) et validation du numéro."""

    def __init__(self, rappel=None, nom_peripherique=None):
        """
        rappel(numero, texte) : appelée à chaque lecture terminée par Entrée.
            numero = int si le format est valide, sinon None.
            ATTENTION : appelée depuis un fil séparé (utiliser un signal Qt).
        nom_peripherique : partie du nom du lecteur (voir lister_peripheriques()).
        """
        self._rappel = rappel
        self._nom = nom_peripherique
        self._peripherique = None
        self._fil = None
        self._actif = False
        self._chiffres = _codes_chiffres()

    # -------------------------------------------------------------- validation
    @staticmethod
    def traiter_saisie(texte: str):
        """Retourne le numéro (int) si le texte contient exactement 6 chiffres, sinon None."""
        if texte is None:
            return None
        texte = texte.strip()
        if re.fullmatch(r"[0-9]{%d}" % LONGUEUR_NUMERO, texte):
            return int(texte)
        return None

    # --------------------------------------------------------------- détection
    @staticmethod
    def lister_peripheriques():
        """Liste (chemin, nom) des périphériques d'entrée : utile pour trouver le lecteur."""
        if evdev is None:
            return []
        return [(chemin, evdev.InputDevice(chemin).name) for chemin in evdev.list_devices()]

    def _trouver(self):
        noms = (self._nom.lower(),) if self._nom else NOMS_PAR_DEFAUT
        for chemin, nom in self.lister_peripheriques():
            if any(mot in nom.lower() for mot in noms):
                return evdev.InputDevice(chemin)
        return None

    def est_disponible(self) -> bool:
        """True si le lecteur est branché et détecté."""
        if self._actif:
            return True
        return evdev is not None and self._trouver() is not None

    # ----------------------------------------------------------------- lecture
    def demarrer(self) -> bool:
        """Réserve le lecteur et lance la lecture en arrière-plan. False si absent."""
        if evdev is None or self._actif:
            return self._actif
        self._peripherique = self._trouver()
        if self._peripherique is None:
            return False
        self._peripherique.grab()       # les frappes ne vont plus au reste du système
        self._actif = True
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()
        return True

    def arreter(self) -> None:
        """Libère le lecteur."""
        self._actif = False
        if self._peripherique is not None:
            try:
                self._peripherique.ungrab()
                self._peripherique.close()   # débloque read_loop()
            except OSError:
                pass
            self._peripherique = None

    def _boucle(self):
        tampon = ""
        try:
            for evenement in self._peripherique.read_loop():
                if not self._actif:
                    break
                # Seulement les appuis de touche (value 1 = enfoncée)
                if evenement.type != ecodes.EV_KEY or evenement.value != 1:
                    continue
                if evenement.code in (ecodes.KEY_ENTER, ecodes.KEY_KPENTER):
                    if tampon and self._rappel is not None:
                        self._rappel(self.traiter_saisie(tampon), tampon)
                    tampon = ""
                elif evenement.code in self._chiffres:
                    tampon += self._chiffres[evenement.code]
                else:
                    tampon += "?"           # caractère non numérique : format invalide
                if len(tampon) > LONGUEUR_MAX_TAMPON:
                    tampon = ""
        except OSError:
            pass                            # lecteur débranché ou fermé
        finally:
            self._actif = False