"""Lecture CAN T06 non bloquante : aucun mouvement, aucune transition inventée.

CAN v1.6 §6 : 0x302 [0xFF] demande les états complets Bas (0x301) et Haut
(0x311). Le protocole n'a pas d'ID de requête : on exige des trames valides
reçues après l'émission locale, sans prétendre dater leur acquisition physique.
"""
import math


class LectureIR:
    def __init__(self, can, horloge, *, delai=1.0):
        if type(delai) not in (int, float) or not math.isfinite(delai) or delai <= 0:
            raise ValueError("Délai de lecture IR positif requis")
        self.can, self.horloge, self.delai = can, horloge, delai
        self.cle = None
        self.etat, self.erreur = 'INACTIVE', ''
        self.defaut_signale = False
        self.frontiere = 0
        self.ouverte_a = self.echeance = None
        self.reponses = set()

    @property
    def en_attente(self):
        return self.etat == 'ATTENTE'

    def commencer(self, cle, frontiere):
        if cle == self.cle:
            return  # un clic répété ne réémet pas et ne prolonge pas le délai
        if self.en_attente:
            raise RuntimeError("Une lecture IR est déjà en attente")
        self.cle, self.frontiere = cle, frontiere
        self.etat, self.erreur = 'ATTENTE', ''
        self.defaut_signale = False
        self.reponses.clear()
        self.ouverte_a = self.horloge()
        self.echeance = self.ouverte_a + self.delai
        try:
            self.can.envoyer(0x302, bytes([0xFF]))
        except Exception as erreur:
            self.echouer(f"Lecture IR non envoyée : {erreur}")

    def concerne(self, ordre):
        return self.en_attente and ordre > self.frontiere

    def accepter(self, identifiant, ordre, recu_a):
        """Appelé uniquement APRÈS validation de la trame complète par T12."""
        if identifiant not in (0x301, 0x311) or not self.concerne(ordre):
            return
        if recu_a < self.ouverte_a:
            return  # callback commencé avant la demande, mais retardé par un verrou
        if recu_a >= self.echeance:
            self.echouer("État complet IR reçu après échéance")
            return
        self.reponses.add(identifiant)
        if self.reponses == {0x301, 0x311}:
            self.etat = 'TERMINEE'

    def actualiser(self):
        if self.en_attente and self.horloge() >= self.echeance:
            manquants = ', '.join(f'0x{i:03X}' for i in sorted({0x301, 0x311} - self.reponses))
            self.echouer(f"État complet IR manquant : {manquants}")

    def echouer(self, raison):
        if self.en_attente:
            self.etat, self.erreur = 'ERREUR', raison

    def annuler(self):
        if self.en_attente:
            self.etat = 'ANNULEE'
