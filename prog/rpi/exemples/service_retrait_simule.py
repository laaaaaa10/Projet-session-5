"""Adaptateur du banc T12 vers le VRAI GestionServiceT13, sans sécurité réelle.

Seul le réarmement et les observations de sécurité sont simulés ici. Les
commandes de service agissent sur les vraies machines T11/T12 du banc.
Une transaction interrompue reste à réconcilier : aucune remise en mouvement.
"""
from dataclasses import replace

from api.service_t13 import ConditionsService
from modules.demande_retrait import EtapeDemandeRetrait as D
from modules.depot import EtapeDepot


class ServiceRetraitSimule:
    simulation = True

    def __init__(self, banc):
        self.banc = banc
        self._rearmement = None

    def conditions(self):
        b = self.banc
        c = b.securite.conditions()
        transaction = 'AUCUNE'
        if b.t12.occupe or b.demande.etape in (D.ATTENTE, D.PAYE, D.INCERTAIN, D.INTERROMPU):
            transaction = 'CONFIRMEE'
        elif b.demande.etape == D.DEMANDE:
            transaction = 'NON_CONFIRMEE'
        if b.t11.occupe or (b.t11.transaction_id is not None and b.t11.etape in (EtapeDepot.DEFAUT, EtapeDepot.INTERROMPU)):
            transaction = 'CONFIRMEE'
        return ConditionsService(
            transaction=transaction, rampe_occupee=b.t12.sortie is not False,
            defauts_leves=c.defauts_leves and (not b.t12.arbitre.bloque or c.intervention_confirmee),
            intervention_confirmee=c.intervention_confirmee,
            bras_retracte_sur=c.bras_retracte_sur,
            reference_verticale=c.reference_verticale, reference_angulaire=c.reference_angulaire)

    def autoriser_nouvelles(self, autoriser):
        self.banc.t12.autoriser_nouvelles(autoriser)

    def annuler_non_confirmee(self):
        d = self.banc.demande
        if d.etape == D.DEMANDE:
            d.annuler(d.id_demande)

    def arreter(self):
        self._rearmement = None
        self.banc.t12.arreter()
        self.banc.t11.arreter()

    def actualiser(self):
        self.banc.t12.mettre_a_jour()
        self.banc.t11.mettre_a_jour()

    def intervention_simulee(self):
        """Action de banc explicite, jamais une confirmation de matériel réel."""
        b = self.banc
        b.can.arrete = False
        b.can.courante = None
        b.can.attentes.clear()
        b.can.niveau = b.can.angle = 0
        b.can.bras = 1
        b.securite.valeurs = replace(b.securite.valeurs, intervention_confirmee=True,
                                    barriere_fermee=True, defauts_leves=True,
                                    bras_retracte_sur=True, reference_verticale=True,
                                    reference_angulaire=True)
        b.can.surveillance()
        b.t12.mettre_a_jour()

    def lancer_rearmement(self, identifiant):
        self._rearmement = (identifiant, self.banc.horloge() + .5)

    def resultat_rearmement(self, identifiant):
        if not self._rearmement or self._rearmement[0] != identifiant or self.banc.horloge() < self._rearmement[1]:
            return None
        b = self.banc
        if self.conditions().obstacles(intervention=True):
            return False
        if b.t11.etape in (EtapeDepot.DEFAUT, EtapeDepot.INTERROMPU):
            b.t11.acquitter_defaut()
        return b.t12.acquitter_intervention()

    def diagnostic(self):
        b = self.banc
        return {"sequence": b.t12.obtenir_etat(), "erreur": b.t12.derniere_erreur,
                "place_liberee_physiquement": b.t12.place_liberee,
                "arrivee_sortie": b.t12.arrivee_sortie, "depart_confirme": b.t12.depart_confirme,
                "simulation": True}
