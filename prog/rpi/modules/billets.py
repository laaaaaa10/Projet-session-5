"""
billets.py - T05 (RPi) : gestion des demandes d'impression des billets.

GestionBillets envoie IMPRESSION_CMD (0x360) et IMPRESSION_DATE (0x361) au
STM32 Borne et suit les réponses IMPRESSION_ETAT (0x230), SANS JAMAIS BLOQUER :
  - demander_impression()      envoie les trames et retourne immédiatement
  - traiter_trame()            est appelée à chaque trame CAN reçue
  - mettre_a_jour()            est appelée périodiquement (délai de réponse)
  - obtenir_etat()             donne l'état d'une demande à l'interface

Le module ne dépend pas directement de python-can : il reçoit une fonction
d'envoi, ce qui permet de le tester sans bus CAN.

Protocole CAN ESA v1.6, section 9.
Projet ESA - 243-557 - Automne 2026
"""
import struct
import threading
import time
from datetime import datetime
from enum import Enum

# --- Identifiants CAN (protocole v1.6) --------------------------------------
ID_IMPRESSION_CMD = 0x360
ID_IMPRESSION_DATE = 0x361
ID_IMPRESSION_ETAT = 0x230

TYPE_BILLET = 0x01
TRANSACTION_MAX = 999_999
NB_PLACES = 14

# --- DB2 de 0x230 : codes d'erreur T05 --------------------------------------
ERREURS = {
    0x00: "aucune", 0x01: "DLC invalide", 0x02: "type invalide",
    0x03: "transaction hors plage", 0x04: "place invalide", 0x05: "date invalide",
    0x06: "trame manquante", 0x07: "imprimante occupée", 0x08: "erreur UART",
    0x09: "délai UART dépassé", 0x0B: "incohérence",
}


class EtatImpression(Enum):
    """État d'une demande, vu par le RPi."""
    EN_ATTENTE = "en attente"            # trames envoyées, aucune réponse
    VALIDEE = "données validées"         # 0x230 résultat 1 : impression lancée
    ENVOYEE = "envoyée"                  # 0x230 résultat 2 : terminé (succès)
    REFUSEE = "refusée"                  # 0x230 résultat 0
    ERREUR = "erreur"                    # 0x230 résultat 3
    SANS_REPONSE = "sans réponse"        # aucun résultat final dans le délai
    INCONNUE = "inconnue"                # séquence jamais demandée

    @property
    def est_finale(self):
        return self in (EtatImpression.ENVOYEE, EtatImpression.REFUSEE,
                        EtatImpression.ERREUR, EtatImpression.SANS_REPONSE)


class _Demande:
    """Suivi interne d'une demande d'impression."""
    def __init__(self, sequence, transaction_id, place, t_envoi):
        self.sequence = sequence
        self.transaction_id = transaction_id
        self.place = place
        self.t_envoi = t_envoi
        self.etat = EtatImpression.EN_ATTENTE
        self.erreur = 0


class GestionBillets:
    """Demandes d'impression vers le STM32 Borne (non bloquant)."""

    def __init__(self, envoyer_trame, delai_reponse_s=5.0, horloge=time.monotonic):
        """
        envoyer_trame(identifiant, donnees) : fonction qui envoie une trame CAN.
        delai_reponse_s : délai maximal pour recevoir un résultat final.
        horloge : source de temps (remplaçable pour les tests).
        """
        self._envoyer = envoyer_trame
        self._delai = delai_reponse_s
        self._horloge = horloge
        self._prochaine_sequence = int(horloge() * 1000) % 256   # départ variable
        self._demandes = {}                 # séquence → _Demande
        self._verrou = threading.Lock()     # réception CAN dans un autre fil

    # ------------------------------------------------------------------ envoi
    def demander_impression(self, transaction_id: int, place: int,
                            horodatage: datetime) -> int:
        """Envoie 0x360 puis 0x361 et retourne la séquence utilisée."""
        if not 0 <= transaction_id <= TRANSACTION_MAX:
            raise ValueError(f"transaction hors plage : {transaction_id}")
        if not 1 <= place <= NB_PLACES:
            raise ValueError(f"place invalide : {place}")

        with self._verrou:
            sequence = self._prochaine_sequence
            self._prochaine_sequence = (sequence + 1) % 256
            self._demandes[sequence] = _Demande(sequence, transaction_id, place,
                                                self._horloge())

        # '<' little-endian, 'B' uint8, 'I' uint32
        cmd = struct.pack("<BBIBB", sequence, TYPE_BILLET, transaction_id, place, 0)
        date = struct.pack("<7B", sequence, horodatage.year - 2000, horodatage.month,
                           horodatage.day, horodatage.hour, horodatage.minute,
                           horodatage.second)
        self._envoyer(ID_IMPRESSION_CMD, cmd)    # les deux trames sont envoyées
        self._envoyer(ID_IMPRESSION_DATE, date)  # immédiatement (< 1 s)
        return sequence

    # -------------------------------------------------------------- réception
    def traiter_trame(self, identifiant: int, donnees: bytes) -> None:
        """À appeler pour CHAQUE trame CAN reçue : ne garde que 0x230 valides."""
        if identifiant == ID_IMPRESSION_ETAT and len(donnees) == 3:
            self.traiter_etat_impression(donnees[0], donnees[1], donnees[2])

    def traiter_etat_impression(self, sequence: int, resultat: int, erreur: int) -> None:
        """Met à jour la demande correspondant à la séquence reçue."""
        with self._verrou:
            demande = self._demandes.get(sequence)
            if demande is None or demande.etat.est_finale:
                return   # séquence inconnue ou demande déjà terminée
            if resultat == 1:
                demande.etat = EtatImpression.VALIDEE
            elif resultat == 2:
                demande.etat = EtatImpression.ENVOYEE
            elif resultat == 0:
                demande.etat = EtatImpression.REFUSEE
            elif resultat == 3:
                demande.etat = EtatImpression.ERREUR
            demande.erreur = erreur

    # ------------------------------------------------------------ surveillance
    def mettre_a_jour(self) -> None:
        """À appeler périodiquement (ex. QTimer) : détecte l'absence de réponse."""
        maintenant = self._horloge()
        with self._verrou:
            for demande in self._demandes.values():
                if (not demande.etat.est_finale
                        and maintenant - demande.t_envoi >= self._delai):
                    demande.etat = EtatImpression.SANS_REPONSE

    # ------------------------------------------------------------- consultation
    def obtenir_etat(self, sequence: int) -> str:
        """État lisible d'une demande (pour l'affichage)."""
        with self._verrou:
            demande = self._demandes.get(sequence)
            if demande is None:
                return EtatImpression.INCONNUE.value
            if demande.etat in (EtatImpression.REFUSEE, EtatImpression.ERREUR):
                return f"{demande.etat.value} ({ERREURS.get(demande.erreur, hex(demande.erreur))})"
            return demande.etat.value

    def etat_brut(self, sequence: int) -> EtatImpression:
        """État sous forme d'énumération (pour la logique)."""
        with self._verrou:
            demande = self._demandes.get(sequence)
            return demande.etat if demande else EtatImpression.INCONNUE


def creer_gestion_billets(service_can, **options) -> GestionBillets:
    """Crée GestionBillets branché sur le service CAN commun :
    envoi par service_can.envoyer, réception des 0x230 par abonnement."""
    billets = GestionBillets(service_can.envoyer, **options)
    service_can.abonner([ID_IMPRESSION_ETAT], billets.traiter_trame)
    return billets
