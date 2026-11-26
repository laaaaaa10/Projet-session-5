"""T12 mécanique non bloquant, à raccorder aux propriétaires T04/T06/T13.

Le callback CAN ne fait qu'enfiler des trames horodatées. Toute progression,
SQLite et facturation restent dans le thread de travail qui appelle actualiser.
Aucun transport, GPIO, lecteur RFID ou affichage n'est créé ici.
"""
from dataclasses import dataclass
from enum import Enum
import json
import math
from pathlib import Path
from queue import Queue, Empty, Full
import sqlite3
import time

from api.mecanique_retrait import ConditionsRetrait, SortieCloturee
from modules.arbitrage_mecanique import arbitre_du_can
from modules.depot import (
    ID_ARRETS, ID_ELEVATION_CMD, ID_ROTATION_CMD, ID_BRAS_CMD,
    ID_ELEVATION_ETAT, ID_ROTATION_ETAT, ID_BRAS_ETAT, REPONSE_DE,
    ELEV_DEPLACER, ELEV_LECTURE, ELEV_SOULEVER, ELEV_ABAISSER,
    ROT_DEPLACER, ROT_LECTURE, BRAS_DEPLOYER, BRAS_RETRACTER, BRAS_LECTURE,
    RES_ACCEPTEE, RES_TERMINEE, RES_REFUSEE, RES_INTERROMPUE, RES_DEFAUT,
)
from modules.stationnement import EtatPlace, Presence

IDS_ECOUTES = (*ID_ARRETS, 0x010, 0x011, 0x012, 0x013, 0x041, 0x042,
               0x200, 0x210, 0x220, 0x300, 0x301, 0x310, 0x311)


class EtapeRetrait(str, Enum):
    INACTIF = "INACTIF"
    PREPARATION = "PREPARATION"
    ACCES = "ACCES"
    PRISE = "PRISE"
    ATTENTE_PLACE = "ATTENTE_ABSENCE_PLACE"
    TRANSPORT = "TRANSPORT_SORTIE"
    RESTITUTION = "RESTITUTION"
    RETOUR = "RETOUR_NIVEAU_0"
    ATTENTE_SORTIE = "ATTENTE_PRESENCE_SORTIE"
    ATTENTE_MANUEL = "ATTENTE_RETRAIT_MANUEL"
    CLOTURE = "CLOTURE_EN_COURS"
    CLOTURE_INCERTAINE = "CLOTURE_INCERTAINE"
    TERMINE = "TERMINE"
    DEFAUT = "DEFAUT"
    INTERROMPU = "INTERROMPU"


@dataclass
class _Commande:
    etape: EtapeRetrait
    identifiant: int
    action: int
    cible: int
    position_attendue: int
    lecture: bool = False
    marque: str = ""
    sequence: int | None = None
    envoyee_a: float = 0
    acceptee_a: float | None = None


class GestionRetrait:
    def __init__(self, can, stationnement, facturation, *, demande, securite,
                 journal, table_ir, ordre_sortie, horloge=time.monotonic,
                 delai_mouvement=30., delai_ir=5., delai_surveillance=1.5):
        # Pas de table physique ni de trajet par défaut : le banc les déclare.
        if (set(table_ir) != set(range(1, 15)) or set(table_ir.values()) != set(range(14))
                or any(type(x) is not int for x in (*table_ir, *table_ir.values()))):
            raise ValueError("Table explicite place 1..14 -> indice IR 0..13 requise")
        if ordre_sortie not in ("rotation_elevation", "elevation_rotation"):
            raise ValueError("Ordre de transport vers la sortie à fournir")
        for valeur in (delai_mouvement, delai_ir, delai_surveillance):
            if type(valeur) not in (int, float) or not math.isfinite(valeur) or valeur <= 0:
                raise ValueError("Délais positifs requis")
        self.can, self.modele, self.facturation = can, stationnement, facturation
        self.demande, self.securite, self.horloge = demande, securite, horloge
        self.arbitre = arbitre_du_can(can)
        self.arbitre.sequences_sans_reemploi = True
        self.table_ir, self.ordre_sortie = dict(table_ir), ordre_sortie
        self._place_par_ir = {i: p for p, i in table_ir.items()}
        self.delai_mouvement, self.delai_ir = delai_mouvement, delai_ir
        self.delai_surveillance = delai_surveillance
        self._reception = Queue(maxsize=256)
        self._debordement = False
        self._hb, self._compteurs, self._places = {}, {}, {}
        self.sortie = None
        self._sortie_observee_a = None
        self._cmd, self._commandes = None, []
        self._niveau = self._angle = self._bras = None
        self.id_demande = self.transaction_id = self.place = None
        self.place_liberee = self.arrivee_sortie = self.depart_confirme = False
        self._prise_ouverte = self._sortie_ouverte = False
        self._limite_place = self._limite_sortie = None
        self.etape, self.derniere_erreur = EtapeRetrait.INACTIF, ""
        self.autoriser_nouvelles(False)
        Path(journal).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(journal)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")
        with self.db:
            self.db.execute('''CREATE TABLE IF NOT EXISTS retraits (
                id TEXT PRIMARY KEY, transaction_id INTEGER NOT NULL,
                place INTEGER NOT NULL, etape TEXT NOT NULL, details TEXT NOT NULL)''')
            en_cours = self.db.execute("SELECT * FROM retraits WHERE etape != ? ORDER BY rowid DESC LIMIT 1",
                                       (EtapeRetrait.TERMINE.value,)).fetchone()
            if en_cours:
                self.id_demande, self.transaction_id, self.place = (
                    en_cours['id'], en_cours['transaction_id'], en_cours['place'])
                self.etape = EtapeRetrait.INTERROMPU
                self.derniere_erreur = "Redémarrage : aucune reprise ; intervention requise"
                self.arbitre.verrouiller(self.derniere_erreur)
                self.db.execute("UPDATE retraits SET etape=? WHERE etape != ?",
                                (self.etape.value, EtapeRetrait.TERMINE.value))

    @property
    def occupe(self):
        return self.id_demande is not None and self.etape not in (EtapeRetrait.TERMINE, EtapeRetrait.INACTIF)

    def autoriser_nouvelles(self, autoriser):
        self.demande.autoriser_nouvelles(autoriser)
        self.arbitre.nouvelles_autorisees = autoriser

    def demander_retrait(self, transaction_id, *, id_demande):
        if self.occupe:
            return id_demande == self.id_demande and transaction_id == self.transaction_id
        return self.demande.demander_retrait(transaction_id, id_demande=id_demande)

    def confirmer_retrait_et_figer_montant(self, id_demande):
        return self.demande.confirmer_retrait_et_figer_montant(id_demande)

    def autoriser_apres_paiement(self, id_demande):
        try:
            ancien = self.db.execute("SELECT etape FROM retraits WHERE id=?", (id_demande,)).fetchone()
        except sqlite3.Error as erreur:
            self._defaut(f"Journal avant autorisation indisponible : {erreur}")
            return False
        if ancien:
            return ancien['etape'] not in (EtapeRetrait.DEFAUT.value, EtapeRetrait.INTERROMPU.value,
                                           EtapeRetrait.CLOTURE_INCERTAINE.value)
        if self.occupe or not self.demande.paiement_valide or id_demande != self.demande.id_demande:
            return False
        ligne = self.demande.instantane()
        erreur = self._conditions_initiales(ligne['place'])
        if erreur:
            self.derniere_erreur = erreur
            return False
        # Un retrait déjà payé peut finir pendant MISE_HORS_SERVICE ; un arrêt
        # verrouillé bloque toujours, même si le paiement est déjà acquis.
        if not self.arbitre.prendre(self, deja_confirmee=True):
            self.derniere_erreur = "Mécanique occupée ou arrêt verrouillé"
            return False
        self.id_demande, self.transaction_id, self.place = id_demande, ligne['numero'], ligne['place']
        self.place_liberee = self.arrivee_sortie = self.depart_confirme = False
        self._prise_ouverte = self._sortie_ouverte = False
        self._limite_place = self._limite_sortie = None
        self._niveau = self._angle = self._bras = None
        self.derniere_erreur = ""
        self.etape = EtapeRetrait.PREPARATION
        try:
            with self.db:
                self.db.execute("INSERT INTO retraits VALUES (?, ?, ?, ?, '{}')",
                                (id_demande, self.transaction_id, self.place, self.etape.value))
        except Exception as erreur:
            self._defaut(f"Journal avant mouvement : {erreur}")
            return False
        self._commandes = self._construire_sequence()
        self._progresser()
        return self.etape not in (EtapeRetrait.DEFAUT, EtapeRetrait.INTERROMPU)

    def _conditions_initiales(self, place):
        probleme = self._controle_securite()
        if probleme:
            return probleme
        try:
            c = self.securite.conditions()
        except Exception as erreur:
            return f"Sécurité indisponible : {erreur}"
        if c.bras_retracte_sur is not True:
            return "Références ou rétraction non confirmées"
        if self._hb[0x041][1] != 1:
            return "STM32 Haut non disponible"
        p = self._places.get(place)
        if (p is None or p[0] is not True or self.horloge() - p[1] > self.delai_surveillance
                or self.modele.etat(place) != EtatPlace.OCCUPEE):
            return "Place occupée et présence IR fraîche requises"
        if (self.sortie is not False or self._sortie_observee_a is None
                or self.horloge() - self._sortie_observee_a > self.delai_surveillance):
            return "Zone de sortie libre et observation fraîche requises"
        return ""

    def _controle_securite(self):
        try:
            c = self.securite.conditions()
            if (not isinstance(c, ConditionsRetrait) or type(c.observe_a) not in (int, float)
                    or not math.isfinite(c.observe_a)
                    or not 0 <= self.horloge() - c.observe_a <= self.delai_surveillance
                    or c.barriere_fermee is not True or c.defauts_leves is not True
                    or c.parcours_valide is not True or c.reference_verticale is not True
                    or c.reference_angulaire is not True):
                return "Barrière, sécurité ou trajet non validés / observation périmée"
        except Exception as erreur:
            return f"Sécurité indisponible : {erreur}"
        for ident in (0x041, 0x042):
            h = self._hb.get(ident)
            if h is None or h[1] not in (1, 2) or self.horloge() - h[0] >= self.delai_surveillance:
                return f"Surveillance STM32 perdue (0x{ident:03X})"
        return ""

    def _construire_sequence(self):
        E = EtapeRetrait
        niveau, angle = 1 + (self.place - 1) // 7, 1 + (self.place - 1) % 7
        def elev(e, action, cible, attendu, marque="", lecture=False):
            return _Commande(e, ID_ELEVATION_CMD, action, cible, attendu, lecture, marque)
        def rot(e, cible):
            return _Commande(e, ID_ROTATION_CMD, ROT_DEPLACER, cible, cible)
        def bras(e, action, marque=""):
            return _Commande(e, ID_BRAS_CMD, action, 0, 2 if action == BRAS_DEPLOYER else 1, False, marque)
        transport = [rot(E.TRANSPORT, 0), elev(E.TRANSPORT, ELEV_DEPLACER, 1, 1)]
        if self.ordre_sortie == "elevation_rotation":
            transport.reverse()
        return [
            _Commande(E.PREPARATION, ID_BRAS_CMD, BRAS_LECTURE, 0, 1, True),
            elev(E.PREPARATION, ELEV_LECTURE, 0, 0, lecture=True),
            _Commande(E.PREPARATION, ID_ROTATION_CMD, ROT_LECTURE, 255, 0, True),
            elev(E.ACCES, ELEV_DEPLACER, niveau, niveau), rot(E.ACCES, angle),
            bras(E.PRISE, BRAS_DEPLOYER), elev(E.PRISE, ELEV_SOULEVER, 0, niveau, "prise"),
            bras(E.PRISE, BRAS_RETRACTER, "place"), *transport,
            bras(E.RESTITUTION, BRAS_DEPLOYER), elev(E.RESTITUTION, ELEV_ABAISSER, 0, 1, "sortie"),
            bras(E.RESTITUTION, BRAS_RETRACTER), elev(E.RETOUR, ELEV_DEPLACER, 0, 0),
        ]

    def traiter_trame(self, identifiant, donnees):
        if identifiant in IDS_ECOUTES:
            try:
                self._reception.put_nowait((identifiant, bytes(donnees), self.horloge()))
            except Full:
                self._debordement = True

    def traiter_reponse_can(self, message):
        if not any(getattr(message, n, False) for n in ('is_extended_id', 'is_remote_frame', 'is_error_frame')):
            self.traiter_trame(message.arbitration_id, message.data)

    def traiter_presence_ir(self, capteur, present, *, compteur, synchronisation=False):
        """Adaptateur T06 : valeurs logiques validées, compteur CAN conservé."""
        if type(present) is not bool or type(compteur) is not int or not 0 <= compteur <= 255:
            raise ValueError("Présence booléenne et compteur CAN requis")
        if capteur == 'sortie':
            ident, donnees = (0x311, [int(present), compteur, 1]) if synchronisation else (0x310, [0, int(present), compteur])
        elif type(capteur) is int and capteur in self.table_ir and not synchronisation:
            ident, donnees = 0x300, [self.table_ir[capteur], int(present), compteur]
        else:
            raise ValueError("Capteur inconnu ou masque complet requis pour synchronisation Bas")
        self.traiter_trame(ident, bytes(donnees))

    def mettre_a_jour(self):
        try:
            self.demande.mettre_a_jour()
        except Exception as erreur:
            self._defaut(f"Suivi financier indisponible : {erreur}")
            return
        if self._debordement:
            self._defaut("Débordement des événements CAN")
            self._debordement = False
        # Aucun nouvel ordre n'est envoyé pendant le traitement du lot reçu.
        for _ in range(256):
            try:
                ident, donnees, recu_a = self._reception.get_nowait()
            except Empty:
                break
            self._traiter(ident, donnees, recu_a)
        if self._en_progression:
            probleme = self._controle_securite()
            if probleme or self.arbitre.bloque:
                self._defaut(probleme or self.arbitre.raison)
                return
            if self._cmd:
                c = self._cmd
                limite = c.envoyee_a + .5 if c.acceptee_a is None else c.acceptee_a + self.delai_mouvement
                if self.horloge() >= limite:
                    self._defaut("Aucune réponse d'acceptation" if c.acceptee_a is None else "Fin de mouvement manquante")
                    return
            if self._limite_place is not None and not self.place_liberee and self.horloge() >= self._limite_place:
                self._defaut("Absence IR de la place non confirmée")
                return
            if self._limite_sortie is not None and not self.arrivee_sortie and self.horloge() >= self._limite_sortie:
                self._defaut("Présence IR de sortie non confirmée")
                return
            self._progresser()

    actualiser = mettre_a_jour

    @property
    def _en_progression(self):
        return self.occupe and self.etape not in (EtapeRetrait.DEFAUT, EtapeRetrait.INTERROMPU, EtapeRetrait.CLOTURE_INCERTAINE)

    def _traiter(self, ident, d, recu_a):
        if ident in ID_ARRETS:
            self._defaut(f"Arrêt CAN 0x{ident:03X}", interruption=True)
        elif ident in (0x010, 0x011, 0x012, 0x013):
            if len(d) != 4 or d[2] >= 2:
                self._defaut(f"Défaut critique CAN 0x{ident:03X}")
        elif ident in (0x041, 0x042):
            ancien = self._hb.get(ident)
            if self._en_progression and ancien is not None and recu_a - ancien[0] >= self.delai_surveillance:
                self._defaut("Heartbeat revenu après une coupure : intervention requise")
            if len(d) != 2 or d[1] not in (1, 2):
                self._hb.pop(ident, None)
                if self._en_progression:
                    self._defaut("STM32 arrêté, en défaut ou redémarré")
            elif ident not in self._hb or 0 < (d[0] - self._hb[ident][2]) % 256 < 128:
                self._hb[ident] = (recu_a, d[1], d[0])
        elif ident in REPONSE_DE.values():
            self._etat_moteur(ident, d, recu_a)
        else:
            self._etat_ir(ident, d, recu_a)

    def _etat_moteur(self, ident, d, recu_a):
        if not self._en_progression:
            return
        longueur = 5 if ident == ID_ELEVATION_ETAT else 4
        if len(d) != longueur:
            self._defaut("Trame d'état moteur mal formée")
            return
        if d[1] in (RES_DEFAUT, RES_INTERROMPUE) or d[3] != 0:
            self._defaut("Défaut / interruption d'un moteur")
            return
        c = self._cmd
        if d[0] == 255:
            position = {0x200: self._niveau, 0x210: self._angle, 0x220: self._bras}[ident]
            if d[1] != RES_TERMINEE or d[2] != position or (ident == 0x200 and d[4] not in (1, 2)):
                self._defaut("État spontané : position incertaine ou mouvement non demandé")
            return
        if c is None or d[0] != c.sequence or ident != REPONSE_DE[c.identifiant]:
            return
        limite = c.envoyee_a + .5 if c.acceptee_a is None else c.acceptee_a + self.delai_mouvement
        if recu_a > limite:
            self._defaut("Réponse CAN reçue après échéance")
            return
        if d[1] == RES_REFUSEE:
            self._defaut("Commande refusée")
        elif d[1] == RES_ACCEPTEE:
            if c.acceptee_a is None:
                c.acceptee_a = recu_a  # Les doublons ne prolongent jamais le délai.
        elif d[1] == RES_TERMINEE:
            if not c.lecture and c.acceptee_a is None:
                self._defaut("Fin reçue sans acceptation préalable")
                return
            reference = (2,) if c.lecture or c.action == ELEV_DEPLACER else (1, 2)
            if d[2] != c.position_attendue or (ident == 0x200 and d[4] not in reference):
                self._defaut("Position finale / référence incompatible avec la commande")
                return
            if ident == 0x200:
                self._niveau = d[2]
            elif ident == 0x210:
                self._angle = d[2]
            else:
                self._bras = d[2]
            self._cmd = None
            if c.marque == 'place':
                self.etape = EtapeRetrait.ATTENTE_PLACE
                self._limite_place = recu_a + self.delai_ir
            elif c.marque == 'sortie':
                self._limite_sortie = recu_a + self.delai_ir
            self._enregistrer()
        else:
            self._defaut("Résultat moteur invalide")

    def _etat_ir(self, ident, d, recu_a):
        try:
            if ident == 0x300 and len(d) == 3 and d[0] < 14 and d[1] in (0, 1):
                groupe, compteur, synchro = 'bas', d[2], False
                observations = [(self._place_par_ir[d[0]], bool(d[1]))]
            elif ident == 0x301 and len(d) == 4 and d[3] == 1:
                groupe, compteur, synchro = 'bas', d[2], True
                masque = d[0] | (d[1] & 63) << 8
                observations = [(p, bool(masque >> i & 1)) for p, i in self.table_ir.items()]
            elif ident == 0x310 and len(d) == 3 and d[0] == 0 and d[1] in (0, 1):
                groupe, compteur, synchro = 'sortie', d[2], False
                observations = [('sortie', bool(d[1]))]
            elif ident == 0x311 and len(d) == 3 and d[0] in (0, 1) and d[2] == 1:
                groupe, compteur, synchro = 'sortie', d[1], True
                observations = [('sortie', bool(d[0]))]
            else:
                raise ValueError("IR non fiable ou trame mal formée")
            ancien = self._compteurs.get(groupe)
            delta = None if ancien is None else (compteur - ancien) % 256
            if delta is not None and delta > 127:
                return  # ancien événement : aucun effet et aucune fraîcheur ajoutée
            for capteur, present in observations:
                precedent = self.sortie if capteur == 'sortie' else self._places.get(capteur, (None,))[0]
                if delta == 0 and precedent is not None and precedent != present:
                    raise ValueError("Compteur IR répété avec état différent")
                if delta == 0 and not synchro:
                    continue
                changement = delta != 0 and not synchro
                if capteur == 'sortie':
                    self.sortie, self._sortie_observee_a = present, recu_a
                else:
                    self._places[capteur] = (present, recu_a)
                    self.modele.changer_presence(capteur, Presence.PRESENT if present else Presence.ABSENT)
                if not self._en_progression:
                    continue
                if synchro and precedent is not None and precedent != present and capteur in (self.place, 'sortie'):
                    raise ValueError("Changement IR connu seulement par resynchronisation : intervention requise")
                if capteur == self.place:
                    if self.place_liberee and present:
                        raise ValueError("Véhicule à nouveau détecté dans la place libérée physiquement")
                    if not present and changement:
                        if not self._prise_ouverte:
                            raise ValueError("Disparition du véhicule avant la prise")
                        self.place_liberee = True
                elif capteur == 'sortie':
                    if present and not self._sortie_ouverte:
                        raise ValueError("Obstacle sur la rampe avant restitution")
                    if present and self.depart_confirme:
                        raise ValueError("Rampe réoccupée après départ")
                    if changement and self._sortie_ouverte:
                        if present:
                            self.arrivee_sortie = True
                        elif self.arrivee_sortie:
                            self.depart_confirme = True
            self._compteurs[groupe] = compteur
            if self._en_progression:
                self._enregistrer()
        except ValueError as erreur:
            if ident in (0x310, 0x311):
                self.sortie = None
            else:
                self._places.clear()
                for place in self.table_ir:
                    self.modele.changer_presence(place, Presence.INCONNU)
            if self._en_progression:
                self._defaut(str(erreur))

    def _progresser(self):
        if not self._en_progression or self._cmd is not None:
            return
        if self.etape == EtapeRetrait.ATTENTE_PLACE and not self.place_liberee:
            return
        probleme = self._controle_securite()
        if probleme or self.arbitre.bloque:
            self._defaut(probleme or self.arbitre.raison)
            return
        if not self._commandes:
            self.etape = EtapeRetrait.ATTENTE_MANUEL if self.arrivee_sortie else EtapeRetrait.ATTENTE_SORTIE
            if self.arrivee_sortie and self.depart_confirme:
                self._cloturer()
            else:
                self._enregistrer()
            return
        c = self._commandes.pop(0)
        if not c.lecture and (c.identifiant == ID_ROTATION_CMD or c.action == ELEV_DEPLACER) and self._bras != 1:
            self._defaut("Interverrouillage : bras non rétracté")
            return
        try:
            c.sequence, c.envoyee_a = self.arbitre.sequence(), self.horloge()
            self._cmd, self.etape = c, c.etape
            if c.marque == 'prise':
                self._prise_ouverte = True
            if c.marque == 'sortie':
                self._sortie_ouverte = True
            if self._enregistrer():  # intention AVANT toute émission
                self.arbitre.envoyer(self, self.can, c.identifiant, bytes([c.sequence, c.action, c.cible]))
        except Exception as erreur:
            self._defaut(f"Commande non confirmée : {erreur}")

    def _cloturer(self):
        self.etape = EtapeRetrait.CLOTURE
        if not self._enregistrer():
            return
        try:
            recu = self.facturation.cloturer_sortie(self.id_demande, self.transaction_id, self.place)
            self._confirmer_cloture(recu)
        except Exception as erreur:
            self.etape, self.derniere_erreur = EtapeRetrait.CLOTURE_INCERTAINE, str(erreur)
            self._enregistrer()

    def _confirmer_cloture(self, recu):
        if recu != SortieCloturee(self.id_demande, self.transaction_id, self.place):
            raise ValueError("Clôture T04 absente ou non corrélée")
        self.demande.enregistrer_sortie(self.id_demande)
        self.etape = EtapeRetrait.TERMINE
        if self._enregistrer():
            self.arbitre.liberer(self)

    def reconcilier_cloture(self):
        """Action explicite, lecture seule ; aucun rejeu mécanique ou de clôture."""
        if self.etape != EtapeRetrait.CLOTURE_INCERTAINE or self.arbitre.bloque:
            return False
        if (self._controle_securite() or self.sortie is not False
                or (self._niveau, self._angle, self._bras) != (0, 0, 1)
                or self.modele.presence(self.place) != Presence.ABSENT):
            self.derniere_erreur = "Réconciliation bloquée : conditions mécaniques non sûres"
            return False
        try:
            recu = self.facturation.consulter_sortie(self.id_demande)
            self._confirmer_cloture(recu)
            return self.etape == EtapeRetrait.TERMINE
        except Exception as erreur:
            self.derniere_erreur = str(erreur)
            return False

    def _enregistrer(self):
        if self.id_demande is None:
            return True
        try:
            details = json.dumps({"place_liberee": self.place_liberee, "arrivee_sortie": self.arrivee_sortie,
                                  "depart_confirme": self.depart_confirme, "erreur": self.derniere_erreur,
                                  "sequence": None if self._cmd is None else self._cmd.sequence})
            with self.db:
                self.db.execute("UPDATE retraits SET etape=?, details=? WHERE id=?",
                                (self.etape.value, details, self.id_demande))
            return True
        except Exception as erreur:
            self._defaut(f"Journal mécanique indisponible : {erreur}", enregistrer=False)
            return False

    def _defaut(self, raison, *, interruption=False, enregistrer=True):
        if self.etape == EtapeRetrait.TERMINE:
            # Un arrêt ultérieur ne transforme jamais une ancienne sortie en échec.
            self.id_demande = self.transaction_id = self.place = None
        if self.etape == EtapeRetrait.DEFAUT and interruption:
            interruption, raison = False, self.derniere_erreur
        deja = self.etape in (EtapeRetrait.DEFAUT, EtapeRetrait.INTERROMPU)
        self.etape = EtapeRetrait.INTERROMPU if interruption else EtapeRetrait.DEFAUT
        self.derniere_erreur = raison
        self._cmd, self._commandes = None, []
        self.arbitre.verrouiller(raison)
        self.autoriser_nouvelles(False)
        if not deja:
            try:
                # Arrêt prioritaire existant : motif logiciel, source RPi, détail 0.
                self.can.envoyer(0x004, bytes([1, 6, 0]))
            except Exception:
                self.derniere_erreur += " ; envoi arrêt CAN impossible"
        if enregistrer:
            self._enregistrer()

    def arreter(self):
        self._defaut("Arrêt demandé", interruption=True)
        try:
            self.demande.arreter()
        except Exception as erreur:
            self.derniere_erreur += f" ; interruption financière incertaine : {erreur}"
            self._enregistrer()

    def acquitter_intervention(self):
        """Confirmation externe après intervention ; aucune transaction abandonnée n'est rejouée."""
        try:
            c = self.securite.conditions()
            if (self._controle_securite() or c.intervention_confirmee is not True
                    or c.bras_retracte_sur is not True):
                return False
        except Exception:
            return False
        if not self.arbitre.acquitter(self):
            return False
        self.autoriser_nouvelles(False)
        if self.id_demande is None:
            self.etape = EtapeRetrait.INACTIF
        # Une transaction interrompue reste à résoudre, même après le réarmement.
        return True

    def obtenir_etat(self):
        return self.etape.value

    def fermer(self):
        if self._en_progression:
            self.arreter()
        self.db.close()


def creer_gestion_retrait(service_can, stationnement, facturation, **options):
    retrait = GestionRetrait(service_can, stationnement, facturation, **options)
    service_can.abonner(IDS_ECOUTES, retrait.traiter_trame)
    return retrait
