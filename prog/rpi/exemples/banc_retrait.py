"""Banc déterministe T12 : CAN/STM32/T04/T06/barrière/horloge simulés.

Les classes T12, T11, T02 et T13 sont les vraies. Aucune trame n'atteint can0.
La table IR séquentielle et l'ordre de transport ne valent que pour ce banc.
"""
from collections import deque
from dataclasses import replace
from pathlib import Path

from api.mecanique_retrait import ConditionsRetrait, SortieCloturee
from api.retrait import StatutRetrait
from application.borne import Borne
from exemples.facturation_retrait_simulee import FacturationRetraitSimulee
from modules.depot import creer_gestion_depot
from modules.demande_retrait import GestionDemandeRetrait
from modules.gestion_comptes import ServiceComptes
from modules.lecteur_nfc_rfid import EvenementRFID
from modules.retrait import creer_gestion_retrait, EtapeRetrait
from modules.stationnement import ModeleStationnement, EtatPlace, Presence
from stockage.comptes_csv import DepotComptesCSV

TABLE_IR_SIMULEE = {place: place - 1 for place in range(1, 15)}
CARTE = '0000000002'


class HorlogeSimulee:
    def __init__(self):
        self.temps = 75.

    def __call__(self):
        return self.temps


class SecuriteSimulee:
    simulation = True

    def __init__(self, horloge):
        self.horloge = horloge
        self.valeurs = ConditionsRetrait(horloge(), True, True, True, True, True, True, False)

    def conditions(self):
        return replace(self.valeurs, observe_a=self.horloge())


class BusRetraitSimule:
    simulation = True

    def __init__(self, horloge):
        self.horloge = horloge
        self.envoyees, self._abonnements = [], []
        self.attentes = deque()
        self.courante = None
        self.niveau = self.angle = 0
        self.bras = 1
        self.charge = False
        self.rampe = False
        self.places = {p: p == 10 for p in range(1, 15)}
        self.compteur_bas = self.compteur_sortie = self.compteur_hb = 0
        self.ir_place_actif = self.ir_sortie_actif = True
        self.repondre_lecture_ir = True
        self.arrete = False

    def abonner(self, identifiants, rappel):
        self._abonnements.append((set(identifiants), rappel))

    def desabonner(self, rappel):
        self._abonnements = [(ids, cb) for ids, cb in self._abonnements if cb != rappel]

    def emettre(self, ident, donnees):
        for ids, rappel in self._abonnements:
            if ident in ids:
                rappel(ident, bytes(donnees))

    def envoyer(self, ident, donnees):
        d = bytes(donnees)
        self.envoyees.append((ident, d))
        if ident == 0x302 and self.repondre_lecture_ir:
            if d != bytes([0xFF]):
                raise ValueError('Le banc T12 attend une lecture des deux contrôleurs')
            self.synchroniser_ir()
        elif ident == 0x004:
            self.arrete = True
            self.attentes.clear()
            self.courante = None
        elif ident in (0x100, 0x110, 0x120):
            self.attentes.append((ident, d))

    def surveillance(self):
        self.compteur_hb = (self.compteur_hb + 1) % 256
        self.emettre(0x041, [self.compteur_hb, 3 if self.arrete else 2 if self.courante else 1])
        self.emettre(0x042, [self.compteur_hb, 1])

    def synchroniser_ir(self):
        masque = sum(1 << TABLE_IR_SIMULEE[p] for p, present in self.places.items() if present)
        self.emettre(0x301, [masque & 255, masque >> 8, self.compteur_bas, 1])
        self.emettre(0x311, [int(self.rampe), self.compteur_sortie, 1])

    def ir_place(self, place, present):
        self.places[place] = present
        self.compteur_bas = (self.compteur_bas + 1) % 256
        self.emettre(0x300, [TABLE_IR_SIMULEE[place], int(present), self.compteur_bas])

    def ir_sortie(self, present):
        self.rampe = present
        self.compteur_sortie = (self.compteur_sortie + 1) % 256
        self.emettre(0x310, [0, int(present), self.compteur_sortie])

    def reponse(self, commande, resultat, *, position=None, code=0, reference=2):
        ident, d = commande
        valeur = {0x100: self.niveau, 0x110: self.angle, 0x120: self.bras}[ident] if position is None else position
        trame = [d[0], resultat, valeur, code]
        if ident == 0x100:
            trame.append(reference)
        self.emettre({0x100: 0x200, 0x110: 0x210, 0x120: 0x220}[ident], trame)

    def accepter(self):
        if self.courante is not None or not self.attentes:
            return False
        c = self.attentes.popleft()
        ident, d = c
        lecture = d[1] == (3 if ident == 0x120 else 2)
        if self.arrete:
            self.reponse(c, 0, code=1)
        elif lecture:
            self.reponse(c, 2)
        elif (ident == 0x110 or (ident == 0x100 and d[1] == 1)) and self.bras != 1:
            self.reponse(c, 0, code=1)
        else:
            self.courante = c
            self.reponse(c, 1)
        return True

    def terminer(self):
        if self.courante is None:
            return False
        c, self.courante = self.courante, None
        ident, d = c
        action, cible = d[1], d[2]
        if ident == 0x120:
            self.bras = 2 if action == 1 else 1
        elif ident == 0x110:
            self.angle = cible
        elif action == 1:
            self.niveau = cible
        elif action == 3:
            self.charge = True
            if self.niveau in (1, 2) and self.angle in range(1, 8) and self.ir_place_actif:
                self.ir_place((self.niveau - 1) * 7 + self.angle, False)
        elif action == 4:
            self.charge = False
            if self.niveau == 1 and self.angle == 0 and self.ir_sortie_actif:
                self.ir_sortie(True)
            elif self.niveau in (1, 2) and self.angle in range(1, 8):
                self.ir_place((self.niveau - 1) * 7 + self.angle, True)
        self.reponse(c, 2)
        return True


class FacturationSortieSimulee(FacturationRetraitSimulee):
    def __init__(self, paiements, modele, **options):
        super().__init__(paiements, **options)
        self.modele, self.clotures, self.nombre_clotures = modele, {}, 0

    def cloturer_sortie(self, id_retrait, transaction_id, place):
        attendu = SortieCloturee(id_retrait, transaction_id, place)
        if id_retrait in self.clotures:
            if self.clotures[id_retrait] != attendu:
                raise ValueError('Clôture conflictuelle')
            return attendu
        suivi = self.consulter_retrait(id_retrait)
        if (suivi.statut != StatutRetrait.PAYE or suivi.fenetre.transaction.numero != transaction_id
                or suivi.fenetre.transaction.place != place or self.modele.presence(place) != Presence.ABSENT):
            raise ValueError('Transaction payée et place physiquement vide requises')
        # Simulation EN MÉMOIRE : ce n'est pas la transaction durable du vrai T04.
        self.clotures[id_retrait] = attendu
        self.nombre_clotures += 1
        self.modele.changer_etat(place, EtatPlace.LIBRE)
        return attendu

    def consulter_sortie(self, id_retrait):
        return self.clotures.get(id_retrait)


class _AffichageMuet:
    def __getattr__(self, nom):
        return lambda *args, **kwargs: None


class BancRetrait:
    def __init__(self, racine, *, fabrique_can=BusRetraitSimule):
        self.racine = Path(racine)
        self.horloge = HorlogeSimulee()
        self.can = fabrique_can(self.horloge)
        self.securite = SecuriteSimulee(self.horloge)
        self.modele = ModeleStationnement()
        self.modele.changer_etat(10, EtatPlace.OCCUPEE)
        modele_comptes = self.racine / 'modele.csv'
        modele_comptes.write_text(f'id_uart,nom,solde_centimes\n{CARTE},Carte simulée,1000\n', encoding='utf-8')
        self.comptes = ServiceComptes(DepotComptesCSV(self.racine / 'comptes', modele_comptes))
        self.borne = Borne(self.comptes, _AffichageMuet())
        self.t04 = FacturationSortieSimulee(self.borne, self.modele, horloge=self.horloge)
        self.t04.ajouter_transaction(123456, 10, depose_a=0)
        self.demande = GestionDemandeRetrait(self.t04, self.racine / 'paiement.sqlite3')
        self.depots = []
        self.t11 = creer_gestion_depot(self.can, self.modele, lambda *a: self.depots.append(a), horloge=self.horloge)
        self.t12 = creer_gestion_retrait(self.can, self.modele, self.t04, demande=self.demande,
            securite=self.securite, journal=self.racine / 'mecanique.sqlite3',
            table_ir=TABLE_IR_SIMULEE, ordre_sortie='rotation_elevation', horloge=self.horloge)
        self.can.surveillance()
        self.can.synchroniser_ir()
        self.t12.mettre_a_jour()

    def payer(self, id_demande='retrait-1'):
        assert self.t12.demander_retrait(123456, id_demande=id_demande)
        assert self.t12.confirmer_retrait_et_figer_montant(id_demande)
        assert self.t04.avant_presentation()
        try:
            self.borne.traiter_evenement(EvenementRFID('ACCEPTE', 'RFID simulé', CARTE))
        finally:
            self.t04.apres_presentation()
        self.t12.mettre_a_jour()
        assert self.demande.paiement_valide

    def tour(self, secondes=.1, *, surveillance=True):
        # Avancer longtemps simule les heartbeats périodiques, jamais un saut
        # d'horloge maquillant une perte réelle de surveillance.
        restant = secondes
        while True:
            pas = min(.5, restant) if surveillance else restant
            self.horloge.temps += pas
            if surveillance:
                self.can.surveillance()
            self.t12.mettre_a_jour()
            self.t11.mettre_a_jour()
            restant -= pas
            if restant <= 1e-9:
                break

    def mouvement(self):
        self.can.accepter()
        self.tour()
        self.can.terminer()
        self.tour()

    def jusqu_a(self, etape, maximum=50):
        for _ in range(maximum):
            if self.t12.etape == etape:
                return
            if self.t12.etape in (EtapeRetrait.DEFAUT, EtapeRetrait.INTERROMPU):
                raise AssertionError(self.t12.derniere_erreur)
            self.mouvement()
        raise AssertionError(f'État non atteint : {etape}, état actuel {self.t12.etape}')

    def fermer(self):
        self.t12.fermer()
        self.demande.fermer()
