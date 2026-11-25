"""
simulateur_stm32_borne.py - Essais sans matériel : STM32 Borne simulé (T05).

Se branche sur un bus CAN virtuel et répond comme le vrai firmware aux
demandes d'impression : 0x360 + 0x361 de même séquence → 0x230 « données
validées » puis, après le temps d'envoi d'un billet, « envoyée sur UART ».

Usage :
  sim = SimulateurStm32Borne(channel="esa")   # même canal que ServiceCAN virtuel
  sim.demarrer() ... sim.arreter()

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T05)
"""
import threading
import time

ID_CMD, ID_DATE, ID_ETAT = 0x360, 0x361, 0x230
DUREE_IMPRESSION_S = 2.0     # billet avec logo à 9600 bauds


class SimulateurStm32Borne:
    def __init__(self, channel="esa", duree_impression_s=DUREE_IMPRESSION_S):
        self._channel = channel
        self._duree = duree_impression_s
        self._bus = None
        self._fil = None
        self._actif = False
        self._en_attente = {}          # séquence → ensemble des trames reçues

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

    def _repondre(self, sequence, resultat, erreur=0):
        import can
        self._bus.send(can.Message(arbitration_id=ID_ETAT, data=bytes([sequence, resultat, erreur]),
                                   is_extended_id=False))

    def _boucle(self):
        while self._actif:
            message = self._bus.recv(timeout=0.1)
            if message is None or message.arbitration_id not in (ID_CMD, ID_DATE):
                continue
            sequence = message.data[0]
            recues = self._en_attente.setdefault(sequence, set())
            recues.add(message.arbitration_id)
            if recues == {ID_CMD, ID_DATE}:
                del self._en_attente[sequence]
                self._repondre(sequence, 1)
                threading.Timer(self._duree, self._repondre, args=(sequence, 2)).start()
