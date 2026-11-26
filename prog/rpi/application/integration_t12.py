"""Parcours T01/T12 exécuté dans le travailleur T02, sans second lecteur.

Le constructeur réel reste bloqué tant que les propriétaires T04/T06/T13 ne
fournissent pas leurs modules. Les tests injectent un RaccordementRetrait avec
les vraies machines T12/T13 et des partenaires explicitement simulés.
"""
from dataclasses import dataclass
import json

from modules.demande_retrait import EtapeDemandeRetrait as D
from modules.retrait import EtapeRetrait as M


@dataclass(frozen=True)
class VueRetrait:
    id_demande: str
    numero: int
    phase: str
    message: str = ""
    montant_centimes: int | None = None
    expire_a: float | None = None


class RaccordementRetrait:
    """Un propriétaire (travailleur Qt) pour T04, les journaux et la progression.

    etat_service lit le vrai gestionnaire T13 ; il n'autorise rien par défaut.
    Le même T04 doit fournir les instantanés et le garde avant/après chaque
    badge. T13 reste propriétaire de l'autorisation des nouvelles demandes.
    """
    def __init__(self, gestion=None, *, t04=None, etat_service=None, raison="Retrait non raccordé"):
        self.gestion, self.t04 = gestion, t04
        self.etat_service = etat_service or (lambda: "HORS_SERVICE")
        self.raison = raison
        self._confirmation = None
        self._refus = None
        if gestion is not None:
            if gestion.facturation is not t04 or gestion.demande.facturation is not t04:
                raise ValueError("Un seul propriétaire T04 attendu")
            for nom in ("avant_presentation", "apres_presentation"):
                if not callable(getattr(t04, nom, None)):
                    raise ValueError(f"Garde de paiement T04 absent : {nom}")

    def vue(self, id_demande=None):
        if self.gestion is None:
            return None
        g = self.gestion
        ligne = g.demande.instantane(id_demande)
        if ligne is None:
            return None
        phase, message = ligne['etape'], ligne['message']
        if ligne['id'] == g.demande.id_demande:
            if self._confirmation == ligne['id'] and g.demande.etape == D.DEMANDE:
                phase = 'VERIFICATION_IR'
            elif (g.demande.etape == D.PAYE and not g.occupe
                  and g.lecture_ir.cle == (ligne['id'], 'depart') and g.lecture_ir.en_attente):
                phase = 'VERIFICATION_IR_APRES_PAIEMENT'
            if g.demande.etape == D.INTERROMPU and g.derniere_erreur:
                message = g.derniere_erreur
        if self._refus is not None and self._refus[0] == ligne['id']:
            message = self._refus[1]
        if g.id_demande == ligne['id'] and g.etape != M.INACTIF:
            phase, message = g.etape.value, g.derniere_erreur
        fenetre = json.loads(ligne['fenetre']) if ligne['fenetre'] else None
        return VueRetrait(ligne['id'], ligne['numero'], phase, message,
                          None if fenetre is None else fenetre[0],
                          None if fenetre is None else fenetre[2])

    def demander(self, numero, id_demande):
        g = self.gestion
        if g is None:
            return VueRetrait(id_demande, numero, "REFUSE", self.raison)
        # Un ancien ID reste consultable, sans agir sur la demande actuelle.
        if g.demande.instantane(id_demande) is not None:
            if g.demande.instantane(id_demande)['numero'] != numero:
                raise ValueError("ID de retrait réutilisé pour un autre billet")
            return self.vue(id_demande)
        if self.etat_service() != "EN_SERVICE":
            return VueRetrait(id_demande, numero, "REFUSE", "Borne hors service")
        if not g.demander_retrait(numero, id_demande=id_demande):
            return VueRetrait(id_demande, numero, "REFUSE", g.demande.derniere_erreur)
        return self.vue(id_demande)

    def _annuler_avec_raison(self, id_demande, raison):
        self._refus = (id_demande, raison)
        self.annuler(id_demande)
        return self.vue(id_demande)

    def confirmer(self, id_demande):
        g = self.gestion
        if g is None:
            return None
        if id_demande != g.demande.id_demande or g.demande.etape != D.DEMANDE:
            return self.vue(id_demande)
        if self._confirmation == id_demande:
            return self.vue(id_demande)
        # Une ancienne mesure IR ne doit ni autoriser le gel ni empêcher sa
        # préparation : demander de nouvelles observations, sans mouvement.
        raison = ("Borne hors service" if self.etat_service() != "EN_SERVICE" else
                  g.verifier_disponibilite(g.demande.instantane()['place'], avec_ir=False))
        if raison:
            return self._annuler_avec_raison(id_demande, raison)
        self._confirmation = id_demande
        if not g.demander_lecture_ir(id_demande, 'paiement'):
            g.arreter()
            self._confirmation = None
        return self.vue(id_demande)

    def annuler(self, id_demande):
        if self.gestion is None:
            return None
        g = self.gestion
        annule = g.demande.annuler(id_demande)
        if annule and id_demande == g.demande.id_demande:
            g.lecture_ir.annuler()
            self._confirmation = None
        return self.vue(id_demande)

    def _service_permet_suite(self):
        return self.etat_service() in ("EN_SERVICE", "MISE_HORS_SERVICE")

    def lire(self, lecteur):
        """Itérateur consommé par Borne.actualiser : garde pour CHAQUE badge.

        Un refus du garde ne transmet pas le badge à T02. Le finally s'exécute
        après le débit synchrone, avant le badge suivant du même lot. Aucun
        résultat n'est consommé ici ; T04 reste l'unique consommateur.
        """
        for evenement in lecteur.lire():
            g = self.gestion
            if evenement.type != "ACCEPTE" or g is None:
                yield evenement
            elif g.demande.etape == D.ATTENTE:
                if not self._service_permet_suite():
                    g.arreter()
                    continue
                if self.t04.avant_presentation() is True:
                    try:
                        yield evenement
                    finally:
                        self.t04.apres_presentation()
            elif g.demande.etape not in (D.INCERTAIN, D.INTERROMPU, D.PAYE):
                yield evenement

    def actualiser(self):
        g = self.gestion
        if g is None:
            return
        if (g.demande.etape in (D.ATTENTE, D.PAYE, D.INCERTAIN)
                and not self._service_permet_suite()):
            g.arreter()
        g.mettre_a_jour()
        if g.etape in (M.DEFAUT, M.INTERROMPU):
            if g.demande.etape not in (None, D.INTERROMPU, D.ANNULE, D.EXPIRE, D.CLOTURE):
                g.arreter()
            self._confirmation = None
            return
        if self._confirmation is not None:
            identifiant = self._confirmation
            if g.demande.etape != D.DEMANDE:
                g.lecture_ir.annuler()
                self._confirmation = None
            elif self.etat_service() != "EN_SERVICE":
                self._annuler_avec_raison(identifiant, "Borne hors service")
            elif g.lecture_ir.etat == 'TERMINEE':
                self._confirmation = None
                raison = g.verifier_disponibilite(g.demande.instantane()['place'])
                if raison:
                    self._annuler_avec_raison(identifiant, raison)
                else:
                    g.confirmer_retrait_et_figer_montant(identifiant)
        if g.demande.etape == D.INCERTAIN:
            g.arreter()  # aucune reprise automatique d'une réponse financière incertaine
        elif g.demande.paiement_valide and not g.occupe:
            identifiant = g.demande.id_demande
            if g.lecture_ir.cle != (identifiant, 'depart'):
                if not g.demander_lecture_ir(identifiant, 'depart'):
                    g.arreter()
            elif g.lecture_ir.etat == 'TERMINEE':
                if not g.autoriser_apres_paiement(identifiant):
                    # Refus après paiement : intervention, jamais un réessai au timer suivant.
                    g.arreter()

    def fermer(self):
        if self.gestion is not None:
            g = self.gestion
            try:
                if g.demande.etape not in (None, D.ANNULE, D.EXPIRE, D.CLOTURE):
                    g.arreter()
            finally:
                try:
                    g.fermer()
                finally:
                    g.demande.fermer()


class LecteurGardeRetrait:
    """Vue du lecteur existant, sans ouvrir de port ni de fil supplémentaire."""
    def __init__(self, lecteur, retrait):
        self.lecteur, self.retrait = lecteur, retrait

    def lire(self):
        return self.retrait.lire(self.lecteur)


def creer_module_t12(t04, *, dossier, can=None, stationnement=None, depot=None, t13=None):
    """Point d'assemblage réel, appelé DANS le travailleur Qt.

    Aucun simulateur implicite, y compris sous --simulation de T01 : son ancien
    simulateur d'ascenseur ne fournit pas toutes les confirmations de T12.
    Pour activer : créer les journaux T12 ici, sur can/stationnement partagés,
    puis raccorder T13 et fournir les gardes T04, la sécurité et la table IR
    validées. Voir RACCORDEMENT_T12.md. Ne pas remplacer les observations par True.
    """
    if t04 is None:
        raison = "Retrait indisponible : facturation T04 non raccordée. Aucun paiement demandé."
    else:
        raison = ("Retrait indisponible : assemblage T04/T06/T13 et confirmations "
                  "mécaniques non raccordés. Aucun paiement demandé.")
    return RaccordementRetrait(raison=raison)
