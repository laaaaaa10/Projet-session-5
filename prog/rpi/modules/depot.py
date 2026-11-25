"""
depot.py - T11 (RPi) : orchestration de la séquence de dépôt.

Machine à états NON BLOQUANTE (interface T11 v1.3, protocole CAN v1.6) :

  Préparation : lecture bras / élévation / rotation → bras rétracté, niveau 0, angle 0
  Prise       : BRAS déployer → ÉLÉVATION soulever → BRAS rétracter
  Transport   : ÉLÉVATION niveau 1|2 → ROTATION position 1..7
  Dépôt       : BRAS déployer → ÉLÉVATION abaisser
  Retour      : BRAS rétracter → ROTATION 0 → ÉLÉVATION niveau 0

En parallèle du retour, T11 attend la confirmation IR de la place (0x300/0x301).
« Dépôt confirmé » (IR) et « séquence mécanique terminée » sont suivis
SÉPARÉMENT : la facturation démarre une seule fois, à la confirmation IR.

Chaque commande doit être acceptée (≤ 500 ms selon le protocole) puis terminée.
Refus, interruption, défaut, délai dépassé, arrêt CAN ou absence IR → état
DÉFAUT : la progression s'arrête et AUCUN mouvement n'est relancé
automatiquement. T11 ne pilote aucun GPIO moteur (STM32 Haut).

Utilisation :
  depot = creer_gestion_depot(service_can, modele, facturation)
  depot.demarrer(transaction_id, niveau, position)   # True = séquence démarrée
  depot.mettre_a_jour()                              # périodiquement (QTimer)

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T11)
"""
import threading
import time
from datetime import datetime
from enum import Enum

from modules.stationnement import EtatPlace, PLACES_PAR_ETAGE, Presence

# --- Identifiants CAN (protocole v1.6) --------------------------------------------
ID_ARRETS = (0x001, 0x002, 0x003, 0x004)
ID_ELEVATION_CMD, ID_ELEVATION_ETAT = 0x100, 0x200
ID_ROTATION_CMD, ID_ROTATION_ETAT = 0x110, 0x210
ID_BRAS_CMD, ID_BRAS_ETAT = 0x120, 0x220
ID_IR_BAS_CHANGEMENT, ID_IR_BAS_COMPLET = 0x300, 0x301
IDS_ECOUTES = (*ID_ARRETS, ID_ELEVATION_ETAT, ID_ROTATION_ETAT, ID_BRAS_ETAT,
               ID_IR_BAS_CHANGEMENT, ID_IR_BAS_COMPLET)

REPONSE_DE = {ID_ELEVATION_CMD: ID_ELEVATION_ETAT,
              ID_ROTATION_CMD: ID_ROTATION_ETAT,
              ID_BRAS_CMD: ID_BRAS_ETAT}

# Actions (DB1 des *_CMD)
ELEV_ARRET, ELEV_DEPLACER, ELEV_LECTURE, ELEV_SOULEVER, ELEV_ABAISSER = 0, 1, 2, 3, 4
ROT_ARRET, ROT_DEPLACER, ROT_LECTURE = 0, 1, 2
BRAS_ARRET, BRAS_DEPLOYER, BRAS_RETRACTER, BRAS_LECTURE = 0, 1, 2, 3

# Résultats communs (DB1 des *_ETAT)
RES_REFUSEE, RES_ACCEPTEE, RES_TERMINEE, RES_INTERROMPUE, RES_DEFAUT = 0, 1, 2, 3, 4
BRAS_RETRACTE = 1                     # BRAS_ETAT DB2 : 1 rétractée estimée
INCONNU = 0xFF
SEQ_SPONTANEE = 0xFF

# --- Délais configurables (à valider sur banc) -----------------------------------
DELAI_ACCEPTATION_S = 1.0             # protocole : 500 ms + marge pour le RPi
DELAI_MOUVEMENT_S = 30.0              # fin d'un mouvement
DELAI_IR_S = 5.0                      # confirmation IR après la fin de l'abaissement


def indice_ir_par_defaut(niveau: int, position: int) -> int:
    """(niveau, position) → indice du détecteur IR 0..13.
    TODO(équipe) : PROVISOIRE. La table officielle sera fournie avec le câblage
    (protocole v1.6, §6 : elle ne doit pas être inventée). Remplacer en passant
    table_ir=... au constructeur."""
    return (niveau - 1) * PLACES_PAR_ETAGE + (position - 1)


def place_de(niveau: int, position: int) -> int:
    """(1, 1..7) → places 1..7 (E1.x) ; (2, 1..7) → places 8..14 (E2.x)."""
    return (niveau - 1) * PLACES_PAR_ETAGE + position


class EtapeDepot(Enum):
    INACTIF = "inactif"
    PREPARATION = "préparation"
    PRISE = "prise du véhicule"
    TRANSPORT = "transport"
    DEPOT = "dépôt"
    RETOUR = "retour"
    TERMINE = "terminé"
    DEFAUT = "défaut"
    INTERROMPU = "interrompu"


class _Commande:
    """Une étape mécanique : une trame *_CMD et sa réponse *_ETAT attendue."""

    def __init__(self, etape, identifiant, action, parametre, description, lecture=False):
        self.etape = etape
        self.identifiant = identifiant
        self.action = action
        self.parametre = parametre
        self.description = description
        self.lecture = lecture          # lecture d'état : une seule réponse, données vérifiées
        self.sequence = None
        self.acceptee = False
        self.t_depart = 0.0


class GestionDepot:
    """Séquence de dépôt T11 (une seule à la fois)."""

    def __init__(self, can, stationnement, facturation,
                 delai_acceptation_s=DELAI_ACCEPTATION_S, delai_mouvement_s=DELAI_MOUVEMENT_S,
                 delai_ir_s=DELAI_IR_S, table_ir=indice_ir_par_defaut,
                 horloge=time.monotonic, maintenant=datetime.now):
        """
        can           : objet avec envoyer(identifiant, donnees) (ServiceCAN).
        stationnement : ModeleStationnement partagé (place → occupée après IR).
        facturation(transaction_id, horodatage) : début de facturation (T04/T12),
                        appelée UNE SEULE FOIS par dépôt confirmé.
        """
        self._can = can
        self._modele = stationnement
        self._facturation = facturation
        self._delai_acceptation = delai_acceptation_s
        self._delai_mouvement = delai_mouvement_s
        self._delai_ir = delai_ir_s
        self._table_ir = table_ir
        self._horloge = horloge
        self._maintenant = maintenant
        self._verrou = threading.RLock()     # trames CAN (autre fil) + mettre_a_jour (Qt)
        self._sequence = 0
        self._reinitialiser()
        self.etape = EtapeDepot.INACTIF

    def _reinitialiser(self):
        self.transaction_id = None
        self.niveau = self.position = self.place = self.indice_ir = None
        self._commandes = []
        self._courante = None
        self.depot_confirme = False          # présence IR confirmée → facturation démarrée
        self.sequence_terminee = False       # retour mécanique au niveau 0 / angle 0
        self.horodatage_depot = None
        self.derniere_erreur = ""
        self._ir_attendu = False             # vrai dès l'envoi de l'abaissement
        self._t_limite_ir = None             # fixé à la fin de l'abaissement

    # ================================================================ interface T11
    def demarrer(self, transaction_id: int, niveau: int, position: int) -> bool:
        """Démarre la séquence. True = séquence démarrée (pas le dépôt réussi)."""
        with self._verrou:
            if self.occupe:
                self.derniere_erreur = "une opération de dépôt est déjà en cours"
                return False
            if self.etape in (EtapeDepot.DEFAUT, EtapeDepot.INTERROMPU):
                self.derniere_erreur = "défaut non acquitté (position mécanique incertaine)"
                return False
            if niveau not in (1, 2) or not 1 <= position <= PLACES_PAR_ETAGE:
                self.derniere_erreur = f"niveau/position invalides : {niveau}/{position}"
                return False
            place = place_de(niveau, position)
            if self._modele.etat(place) != EtatPlace.RESERVEE:
                self.derniere_erreur = f"place {place} non réservée"
                return False
            if self._modele.presence(place) != Presence.ABSENT:
                self.derniere_erreur = f"présence IR dans la place {place}"
                return False

            self._reinitialiser()
            self.transaction_id = transaction_id
            self.niveau, self.position, self.place = niveau, position, place
            self.indice_ir = self._table_ir(niveau, position)
            self._commandes = self._construire_sequence(niveau, position)
            self._lancer_suivante()
            return True

    def mettre_a_jour(self) -> None:
        """Surveille les délais. À appeler périodiquement (100-250 ms)."""
        with self._verrou:
            if not self.occupe:
                return
            maintenant = self._horloge()
            cmd = self._courante
            if cmd is not None:
                ecoule = maintenant - cmd.t_depart
                if not cmd.acceptee and ecoule > self._delai_acceptation:
                    self._defaut(f"{cmd.description} : aucune réponse du STM32 Haut")
                    return
                if cmd.acceptee and ecoule > self._delai_mouvement:
                    self._envoyer_arret(cmd)
                    self._defaut(f"{cmd.description} : délai de fin dépassé")
                    return
            if (self._t_limite_ir is not None and not self.depot_confirme
                    and maintenant > self._t_limite_ir):
                self._defaut("aucune présence IR après l'abaissement", place_en_defaut=True)

    def traiter_reponse_can(self, message) -> None:
        """Accepte un can.Message (interface T11 proposée)."""
        self.traiter_trame(message.arbitration_id, bytes(message.data))

    def traiter_trame(self, identifiant: int, donnees: bytes) -> None:
        """Rappel du ServiceCAN (fil de réception CAN)."""
        with self._verrou:
            if identifiant in ID_ARRETS:
                if self.occupe:
                    self.etape = EtapeDepot.INTERROMPU
                    self.derniere_erreur = f"arrêt reçu (ID 0x{identifiant:03X})"
                    self._courante = None
            elif identifiant == ID_IR_BAS_CHANGEMENT and len(donnees) >= 2:
                self.traiter_presence_ir(donnees[0], donnees[1] == 1)
            elif identifiant == ID_IR_BAS_COMPLET and len(donnees) >= 4:
                if donnees[3] == 1 and self.indice_ir is not None:    # validité globale
                    masque = donnees[0] | (donnees[1] & 0x3F) << 8
                    self.traiter_presence_ir(self.indice_ir, bool(masque >> self.indice_ir & 1))
            elif identifiant in REPONSE_DE.values():
                self._traiter_etat_moteur(identifiant, donnees)

    def traiter_presence_ir(self, indice: int, present: bool) -> None:
        """État IR logique validé par le STM32 Bas (indice 0..13)."""
        with self._verrou:
            if indice != self.indice_ir or self.place is None:
                return
            self._modele.changer_presence(self.place, Presence.PRESENT if present else Presence.ABSENT)
            if present and self._ir_attendu and not self.depot_confirme and self.occupe:
                self._confirmer_depot()

    def arreter(self) -> None:
        """Arrêt demandé (T13 / opérateur) : arrête l'actionneur en cours, sans reprise."""
        with self._verrou:
            if not self.occupe:
                return
            if self._courante is not None:
                self._envoyer_arret(self._courante)
            self.etape = EtapeDepot.INTERROMPU
            self.derniere_erreur = "arrêt demandé"
            self._courante = None

    def acquitter_defaut(self) -> bool:
        """Après vérification manuelle de la mécanique (T13 / opérateur) : permet un
        nouveau dépôt. Ne lance AUCUN mouvement."""
        with self._verrou:
            if self.etape not in (EtapeDepot.DEFAUT, EtapeDepot.INTERROMPU):
                return False
            self.etape = EtapeDepot.INACTIF
            return True

    def obtenir_etat(self) -> str:
        with self._verrou:
            if self.etape in (EtapeDepot.DEFAUT, EtapeDepot.INTERROMPU):
                return f"{self.etape.value} : {self.derniere_erreur}"
            if self._courante is not None:
                return f"{self.etape.value} : {self._courante.description}"
            if self.etape == EtapeDepot.RETOUR and self.sequence_terminee:
                return "retour terminé : attente de la confirmation IR"
            return self.etape.value

    @property
    def occupe(self) -> bool:
        """Une séquence est en cours (opération mécanique unique)."""
        return self.etape not in (EtapeDepot.INACTIF, EtapeDepot.TERMINE,
                                  EtapeDepot.DEFAUT, EtapeDepot.INTERROMPU)

    # ================================================================ interne
    @staticmethod
    def _construire_sequence(niveau, position):
        E = EtapeDepot
        return [
            _Commande(E.PREPARATION, ID_BRAS_CMD, BRAS_LECTURE, 0, "lecture du bras", lecture=True),
            _Commande(E.PREPARATION, ID_ELEVATION_CMD, ELEV_LECTURE, 0, "lecture de l'élévation", lecture=True),
            _Commande(E.PREPARATION, ID_ROTATION_CMD, ROT_LECTURE, INCONNU, "lecture de la rotation", lecture=True),
            _Commande(E.PRISE, ID_BRAS_CMD, BRAS_DEPLOYER, 0, "déploiement du bras"),
            _Commande(E.PRISE, ID_ELEVATION_CMD, ELEV_SOULEVER, 0, "soulèvement du véhicule"),
            _Commande(E.PRISE, ID_BRAS_CMD, BRAS_RETRACTER, 0, "rétraction du bras"),
            _Commande(E.TRANSPORT, ID_ELEVATION_CMD, ELEV_DEPLACER, niveau, f"montée au niveau {niveau}"),
            _Commande(E.TRANSPORT, ID_ROTATION_CMD, ROT_DEPLACER, position, f"rotation vers la position {position}"),
            _Commande(E.DEPOT, ID_BRAS_CMD, BRAS_DEPLOYER, 0, "déploiement du bras"),
            _Commande(E.DEPOT, ID_ELEVATION_CMD, ELEV_ABAISSER, 0, "abaissement du véhicule"),
            _Commande(E.RETOUR, ID_BRAS_CMD, BRAS_RETRACTER, 0, "rétraction du bras"),
            _Commande(E.RETOUR, ID_ROTATION_CMD, ROT_DEPLACER, 0, "rotation vers la position 0"),
            _Commande(E.RETOUR, ID_ELEVATION_CMD, ELEV_DEPLACER, 0, "descente au niveau 0"),
        ]

    def _nouvelle_sequence(self):
        self._sequence = (self._sequence + 1) % 256
        if self._sequence == SEQ_SPONTANEE:          # 0xFF réservé aux états spontanés
            self._sequence = 0
        return self._sequence

    def _lancer_suivante(self):
        if not self._commandes:
            self._courante = None
            self.sequence_terminee = True
            if self.depot_confirme:
                self.etape = EtapeDepot.TERMINE
            return
        cmd = self._commandes.pop(0)
        cmd.sequence = self._nouvelle_sequence()
        cmd.t_depart = self._horloge()
        self._courante = cmd
        self.etape = cmd.etape
        if cmd.identifiant == ID_ELEVATION_CMD and cmd.action == ELEV_ABAISSER:
            self._ir_attendu = True                   # le véhicule peut être détecté en descendant
        try:
            self._can.envoyer(cmd.identifiant, bytes([cmd.sequence, cmd.action, cmd.parametre]))
        except Exception as erreur:
            self._defaut(f"{cmd.description} : envoi CAN impossible ({erreur})")

    def _traiter_etat_moteur(self, identifiant, donnees):
        cmd = self._courante
        if (cmd is None or len(donnees) < 4 or REPONSE_DE[cmd.identifiant] != identifiant
                or donnees[0] != cmd.sequence):
            return                                    # état spontané ou autre commande
        resultat = donnees[1]
        if resultat == RES_REFUSEE:
            self._defaut(f"{cmd.description} : refusée (code {donnees[3]})")
        elif resultat in (RES_INTERROMPUE, RES_DEFAUT):
            mot = "interrompue" if resultat == RES_INTERROMPUE else "défaut"
            self._defaut(f"{cmd.description} : {mot} (code {donnees[3]})")
        elif cmd.lecture and resultat in (RES_ACCEPTEE, RES_TERMINEE):
            probleme = self._verifier_lecture(identifiant, donnees)
            if probleme:
                self._defaut(f"préparation : {probleme}")
            else:
                self._lancer_suivante()
        elif resultat == RES_ACCEPTEE:
            cmd.acceptee = True
            cmd.t_depart = self._horloge()            # le délai de fin commence ici
        elif resultat == RES_TERMINEE:
            fin_abaissement = cmd.identifiant == ID_ELEVATION_CMD and cmd.action == ELEV_ABAISSER
            if fin_abaissement and not self.depot_confirme:
                self._t_limite_ir = self._horloge() + self._delai_ir
            self._lancer_suivante()

    @staticmethod
    def _verifier_lecture(identifiant, donnees):
        """Préconditions : bras rétracté, ascenseur au niveau 0, orientation 0."""
        if identifiant == ID_BRAS_ETAT and donnees[2] != BRAS_RETRACTE:
            return "bras non rétracté"
        if identifiant == ID_ELEVATION_ETAT:
            if len(donnees) < 5 or donnees[2] != 0 or donnees[4] == 0:
                return "ascenseur non référencé au niveau 0"
        if identifiant == ID_ROTATION_ETAT and donnees[2] != 0:
            return "rotation non référencée à la position 0"
        return ""

    def _confirmer_depot(self):
        self.depot_confirme = True
        self._t_limite_ir = None
        self.horodatage_depot = self._maintenant()
        self._modele.changer_etat(self.place, EtatPlace.OCCUPEE)
        try:
            self._facturation(self.transaction_id, self.horodatage_depot)
        except Exception as erreur:
            self.derniere_erreur = f"facturation : {erreur}"     # dépôt réel : on ne recommence pas
        if self.sequence_terminee:
            self.etape = EtapeDepot.TERMINE

    def _envoyer_arret(self, cmd):
        action = {ID_ELEVATION_CMD: ELEV_ARRET, ID_ROTATION_CMD: ROT_ARRET, ID_BRAS_CMD: BRAS_ARRET}
        parametre = INCONNU if cmd.identifiant == ID_ROTATION_CMD else 0
        try:
            self._can.envoyer(cmd.identifiant,
                              bytes([self._nouvelle_sequence(), action[cmd.identifiant], parametre]))
        except Exception:
            pass                                      # le défaut est signalé de toute façon

    def _defaut(self, raison, place_en_defaut=False):
        self.etape = EtapeDepot.DEFAUT
        self.derniere_erreur = raison
        self._courante = None
        self._commandes = []                          # aucune relance automatique
        self._t_limite_ir = None
        if place_en_defaut and self.place is not None:
            self._modele.changer_etat(self.place, EtatPlace.DEFAUT)


def creer_gestion_depot(service_can, stationnement, facturation, **options) -> GestionDepot:
    """Crée T11 et l'abonne aux trames qui le concernent sur le service CAN commun."""
    depot = GestionDepot(service_can, stationnement, facturation, **options)
    service_can.abonner(IDS_ECOUTES, depot.traiter_trame)
    return depot
