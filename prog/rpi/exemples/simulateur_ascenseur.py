"""
simulateur_ascenseur.py - Essais T11 sans mécanique : STM32 Haut (ascenseur)
et détecteurs IR du STM32 Bas simulés sur un bus CAN virtuel.

Réponses conformes au protocole v1.6 :
  - *_CMD → *_ETAT « acceptée » immédiatement, puis « terminée » après la durée
    du mouvement ; une lecture d'état répond « terminée » avec la position ;
  - interverrouillage : rotation ou changement de niveau REFUSÉS si le bras
    n'est pas rétracté ; un seul mouvement à la fois ;
  - après un abaissement aux niveaux 1-2 : IR_BAS_CHANGEMENT (0x300) présence
    pour l'indice de la place (sauf si ir_actif=False, pour essayer l'anomalie).

Usage :
  sim = SimulateurAscenseur(channel="esa")   # même canal que ServiceCAN virtuel
  sim.demarrer() ... sim.arreter()

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T11)
"""
import threading
import time

ID_ELEV_CMD, ID_ROT_CMD, ID_BRAS_CMD = 0x100, 0x110, 0x120
ID_ELEV_ETAT, ID_ROT_ETAT, ID_BRAS_ETAT = 0x200, 0x210, 0x220
ID_IR_BAS_CHANGEMENT = 0x300
REFUSEE, ACCEPTEE, TERMINEE = 0, 1, 2
BRAS_INCONNU, BRAS_RETRACTE, BRAS_DEPLOYE, BRAS_MOUVEMENT = 0, 1, 2, 3
CODE_BRAS_NON_RETRACTE = 0x01
CODE_OCCUPE = 0x02
CODE_INVALIDE = 0x03


class SimulateurAscenseur:
    def __init__(self, channel="esa", duree_mouvement_s=0.6, ir_actif=True):
        self._channel = channel
        self._duree = duree_mouvement_s
        self.ir_actif = ir_actif
        self.niveau, self.angle, self.bras = 0, 0, BRAS_RETRACTE
        self._occupe = False
        self._compteur_ir = 0
        self._bus = None
        self._fil = None
        self._actif = False
        self.journal = []                      # commandes reçues (pour l'affichage)

    def demarrer(self):
        import can
        self._bus = can.Bus(interface="virtual", channel=self._channel)
        self._actif = True
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()

    def arreter(self):
        self._actif = False
        if self._fil is not None:
            self._fil.join(timeout=1)
        if self._bus is not None:
            self._bus.shutdown()

    # ------------------------------------------------------------------ envoi
    def _envoyer(self, identifiant, donnees):
        import can
        if self._actif:
            self._bus.send(can.Message(arbitration_id=identifiant, data=bytes(donnees),
                                       is_extended_id=False))

    def _etat_elev(self, seq, res, code=0):
        self._envoyer(ID_ELEV_ETAT, [seq, res, self.niveau, code, 2])

    def _etat_rot(self, seq, res, code=0):
        self._envoyer(ID_ROT_ETAT, [seq, res, self.angle, code])

    def _etat_bras(self, seq, res, code=0):
        self._envoyer(ID_BRAS_ETAT, [seq, res, self.bras, code])

    # -------------------------------------------------------------- réception
    def _boucle(self):
        while self._actif:
            message = self._bus.recv(timeout=0.1)
            if message is None or len(message.data) < 3:
                continue
            seq, action, param = message.data[0], message.data[1], message.data[2]
            ident = message.arbitration_id
            if ident in (ID_ELEV_CMD, ID_ROT_CMD, ID_BRAS_CMD):
                self.journal.append((hex(ident), action, param))
                self._traiter(ident, seq, action, param)

    def _traiter(self, ident, seq, action, param):
        repondre = {ID_ELEV_CMD: self._etat_elev, ID_ROT_CMD: self._etat_rot,
                    ID_BRAS_CMD: self._etat_bras}[ident]
        lecture = {ID_ELEV_CMD: 2, ID_ROT_CMD: 2, ID_BRAS_CMD: 3}[ident]
        if action == lecture:
            repondre(seq, TERMINEE)
            return
        if action == 0:                                   # arrêt
            self._occupe = False
            repondre(seq, TERMINEE)
            return
        if self._occupe:
            repondre(seq, REFUSEE, CODE_OCCUPE)
            return

        if ident == ID_BRAS_CMD and action in (1, 2):
            fin = lambda: setattr(self, "bras", BRAS_DEPLOYE if action == 1 else BRAS_RETRACTE)
        elif ident == ID_ELEV_CMD and action == 1 and param in (0, 1, 2):
            if self.bras != BRAS_RETRACTE:
                repondre(seq, REFUSEE, CODE_BRAS_NON_RETRACTE)
                return
            fin = lambda: setattr(self, "niveau", param)
        elif ident == ID_ELEV_CMD and action in (3, 4):   # petits déplacements, bras déployé permis
            fin = (lambda: self._detecter_vehicule()) if action == 4 else (lambda: None)
        elif ident == ID_ROT_CMD and action == 1 and 0 <= param <= 7:
            if self.bras != BRAS_RETRACTE:
                repondre(seq, REFUSEE, CODE_BRAS_NON_RETRACTE)
                return
            fin = lambda: setattr(self, "angle", param)
        else:
            repondre(seq, REFUSEE, CODE_INVALIDE)
            return

        self._occupe = True
        if ident == ID_BRAS_CMD:
            self.bras = BRAS_MOUVEMENT
        repondre(seq, ACCEPTEE)

        def terminer():
            if not self._occupe:                          # arrêté entre-temps
                return
            fin()
            self._occupe = False
            repondre(seq, TERMINEE)
        threading.Timer(self._duree, terminer).start()

    def _detecter_vehicule(self):
        """Le véhicule repose sur le PCB : le STM32 Bas signale la présence."""
        if self.ir_actif and self.niveau in (1, 2) and 1 <= self.angle <= 7:
            indice = (self.niveau - 1) * 7 + (self.angle - 1)      # même table provisoire que T11
            self._compteur_ir = (self._compteur_ir + 1) % 256
            threading.Timer(0.2, self._envoyer,
                            args=(ID_IR_BAS_CHANGEMENT, [indice, 1, self._compteur_ir])).start()


if __name__ == "__main__":
    sim = SimulateurAscenseur()
    sim.demarrer()
    print("Simulateur ascenseur actif sur le bus virtuel « esa » (Ctrl+C pour quitter)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sim.arreter()
