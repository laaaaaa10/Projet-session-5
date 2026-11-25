"""
barriere.py - T03 (RPi) : commande du servomoteur de la barrière d'entrée.

Le servo DFRobot SER0006 est branché sur la sortie PWM1 (connecteur P1) du
HAT Pi-CAN-PWM, commandée par un PCA9685 sur le bus I²C 1 (adresse 0x40).

  - Pca9685            pilote minimal du contrôleur PWM (quelques registres)
  - CommandeBarriere   ouvrir() / fermer() / est_ouverte(), non bloquant

Sans capteur de position, l'état de la barrière est ESTIMÉ : il est considéré
atteint après la durée de mouvement configurée (TEMPS_MOUVEMENT_S).
Un mode simulé permet de tester sans matériel.

Projet ESA - 243-557 - Automne 2026
"""
import time
from enum import Enum

# --- Paramètres à calibrer sur banc -----------------------------------------
BUS_I2C = 1
ADRESSE_PCA9685 = 0x40
CANAL_SERVO = 0                 # PWM1 / connecteur P1 = sortie LED0 du PCA9685
FREQUENCE_PWM_HZ = 50
IMPULSION_FERMEE_US = 2000      # barrière fermée (à calibrer)
IMPULSION_OUVERTE_US = 450     # barrière ouverte (à calibrer)
TEMPS_MOUVEMENT_S = 0.6         # 180° en ~0,36 s (0,12 s / 60°) + marge

# --- Registres du PCA9685 ----------------------------------------------------
_MODE1 = 0x00
_MODE2 = 0x01
_LED0_ON_L = 0x06
_PRE_SCALE = 0xFE
_MODE1_SLEEP = 0x10
_MODE1_AI = 0x20                # incrémentation automatique des registres
_MODE1_RESTART = 0x80
_MODE2_OUTDRV = 0x04            # sorties totem-pole
_HORLOGE_INTERNE_HZ = 25_000_000


class Pca9685:
    """Pilote minimal du PCA9685 (16 sorties PWM 12 bits)."""

    def __init__(self, bus=BUS_I2C, adresse=ADRESSE_PCA9685, frequence_hz=FREQUENCE_PWM_HZ):
        from smbus2 import SMBus        # importé ici : le mode simulé n'en a pas besoin
        self._bus = SMBus(bus)
        self._adresse = adresse
        # Prédiviseur : f = 25 MHz / (4096 x (prescale + 1))
        prescale = round(_HORLOGE_INTERNE_HZ / (4096 * frequence_hz)) - 1
        self.periode_us = 1_000_000 * 4096 * (prescale + 1) / _HORLOGE_INTERNE_HZ

        self._ecrire(_MODE1, _MODE1_SLEEP)          # le prédiviseur se règle en veille
        self._ecrire(_PRE_SCALE, prescale)
        self._ecrire(_MODE2, _MODE2_OUTDRV)
        self._ecrire(_MODE1, _MODE1_AI)             # réveil
        time.sleep(0.001)                           # oscillateur stable (500 µs min.)
        self._ecrire(_MODE1, _MODE1_AI | _MODE1_RESTART)

    def _ecrire(self, registre, valeur):
        self._bus.write_byte_data(self._adresse, registre, valeur)

    def regler_impulsion(self, canal: int, largeur_us: float) -> None:
        """Impulsion de largeur_us au début de chaque période sur le canal 0-15."""
        compte = int(round(largeur_us * 4096 / self.periode_us))
        compte = max(0, min(4095, compte))
        # ON = 0 (début de période), OFF = compte
        self._bus.write_i2c_block_data(self._adresse, _LED0_ON_L + 4 * canal,
                                       [0, 0, compte & 0xFF, compte >> 8])

    def eteindre(self, canal: int) -> None:
        """Sortie toujours à 0 (bit FULL_OFF) : le servo n'est plus commandé."""
        self._bus.write_i2c_block_data(self._adresse, _LED0_ON_L + 4 * canal,
                                       [0, 0, 0, 0x10])

    def fermer(self):
        self._bus.close()


class EtatBarriere(Enum):
    INCONNUE = "inconnue"          # démarrage : position jamais commandée
    FERMEE = "fermée"
    OUVERTE = "ouverte"
    OUVERTURE = "ouverture en cours"
    FERMETURE = "fermeture en cours"


class CommandeBarriere:
    """Commande non bloquante de la barrière (état estimé, sans capteur)."""

    def __init__(self, simulation=False, verifier_securite=None, horloge=time.monotonic):
        """
        simulation : True pour tester sans PCA9685.
        verifier_securite() -> (bool, str) : conditions d'ouverture fournies par
            la séquence de dépôt (rampe, mouvement en cours, arrêt verrouillé).
        """
        self._pwm = None if simulation else Pca9685()
        self._verifier = verifier_securite
        self._horloge = horloge
        self._etat = EtatBarriere.INCONNUE
        self._t_debut = 0.0
        self.derniere_raison = ""

    # --------------------------------------------------------- commandes
    def ouvrir(self) -> bool:
        """Lance l'ouverture ; False (sans mouvement) si les conditions ne sont pas remplies."""
        if self._verifier is not None:
            permis, raison = self._verifier()
            if not permis:
                self.derniere_raison = raison
                return False
        self._commander(IMPULSION_OUVERTE_US, EtatBarriere.OUVERTURE)
        return True

    def fermer(self) -> bool:
        """Lance la fermeture (toujours permise : position sûre)."""
        self._commander(IMPULSION_FERMEE_US, EtatBarriere.FERMETURE)
        return True

    def _commander(self, largeur_us, etat_mouvement):
        if self._pwm is not None:
            self._pwm.regler_impulsion(CANAL_SERVO, largeur_us)
        self._etat = etat_mouvement
        self._t_debut = self._horloge()
        self.derniere_raison = ""

    # ------------------------------------------------------------ état
    def mettre_a_jour(self) -> None:
        """À appeler périodiquement : fin du mouvement estimée après TEMPS_MOUVEMENT_S."""
        if (self._etat in (EtatBarriere.OUVERTURE, EtatBarriere.FERMETURE)
                and self._horloge() - self._t_debut >= TEMPS_MOUVEMENT_S):
            self._etat = (EtatBarriere.OUVERTE if self._etat == EtatBarriere.OUVERTURE
                          else EtatBarriere.FERMEE)

    def etat(self) -> EtatBarriere:
        self.mettre_a_jour()
        return self._etat

    def est_ouverte(self):
        """True / False selon l'état ESTIMÉ ; None si inconnu ou en mouvement.
        Ne prouve pas la position physique (aucun capteur)."""
        etat = self.etat()
        if etat == EtatBarriere.OUVERTE:
            return True
        if etat == EtatBarriere.FERMEE:
            return False
        return None

    def liberer(self) -> None:
        """Arrête la commande du servo (fin du programme)."""
        if self._pwm is not None:
            self._pwm.eteindre(CANAL_SERVO)
            self._pwm.fermer()
