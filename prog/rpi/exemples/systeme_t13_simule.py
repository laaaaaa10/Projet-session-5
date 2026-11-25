"""Double explicite T03/T11/T12 et securite CAN, sans pilote materiel."""

from dataclasses import asdict
import json
from pathlib import Path
import time

from api.service_t13 import ConditionsService

SCENARIOS = ("reservation", "depot", "retrait", "fin-sequence", "retirer-vehicule",
             "intervention", "defaut", "reference-invalide", "rearmement-ok",
             "rearmement-refuse", "rearmement-muet")


class SystemeT13Simule:
    simulation = True

    def __init__(self, scenario=None, *, horloge=time.monotonic):
        self.horloge = horloge
        self.scenario = None if scenario is None else Path(scenario)
        self._evenement = None
        # Un ancien ordre local ne doit jamais redemarrer une sequence.
        if self.scenario and self.scenario.exists():
            self._evenement = json.loads(self.scenario.read_text())["id"]
        self.nouvelles = False
        self.transaction = "AUCUNE"
        self.sequence = "INACTIVE"
        self.rampe = False
        self.defauts_leves = True
        self.intervention = False
        self.references = True
        self.bras_sur = True
        self.mode_rearmement = "ok"
        self._rearmement = None
        self.demarrages = self.arrets = self.rearmements = self.annulations = 0
        self.dernier_evenement = "Banc au repos"

    def conditions(self):
        return ConditionsService(self.transaction, self.rampe, self.defauts_leves,
                                 self.intervention, self.bras_sur, self.references, self.references)

    def autoriser_nouvelles(self, autoriser):
        self.nouvelles = autoriser

    def annuler_non_confirmee(self):
        if self.transaction == "NON_CONFIRMEE":
            self.transaction = "AUCUNE"
            self.sequence = "INACTIVE"
            self.annulations += 1

    def arreter(self):
        self.nouvelles = False
        self.arrets += 1
        self.sequence = "INTERROMPUE" if self.transaction != "AUCUNE" else "INACTIVE"
        self.transaction = "AUCUNE"
        self.references = self.bras_sur = self.intervention = False
        self._rearmement = None

    def lancer_rearmement(self, identifiant):
        self.rearmements += 1
        self._rearmement = (identifiant, self.horloge() + 0.5)

    def resultat_rearmement(self, identifiant):
        if (not self._rearmement or self._rearmement[0] != identifiant
                or self.horloge() < self._rearmement[1] or self.mode_rearmement == "muet"):
            return None
        return self.mode_rearmement == "ok"

    def injecter(self, action):
        if action not in SCENARIOS:
            raise ValueError("Scenario inconnu")
        self.dernier_evenement = action
        if action in {"reservation", "depot", "retrait"}:
            if not self.nouvelles or self.transaction != "AUCUNE" or self.rampe:
                self.dernier_evenement = "REFUSE : nouvelle transaction interdite"
                return
            self.transaction = "NON_CONFIRMEE" if action == "reservation" else "CONFIRMEE"
            self.sequence = {"reservation": "RESERVATION", "depot": "DEPOT_T11", "retrait": "RETRAIT_T12"}[action]
            self.rampe = action == "reservation"
            if action != "reservation":
                self.demarrages += 1
        elif action == "fin-sequence":
            if self.sequence == "RETRAIT_T12":
                self.sequence, self.rampe = "ATTENTE_RETRAIT_MANUEL", True
            elif self.sequence == "DEPOT_T11":
                self.sequence, self.transaction = "INACTIVE", "AUCUNE"
        elif action == "retirer-vehicule":
            self.rampe = False
            if self.sequence == "ATTENTE_RETRAIT_MANUEL":
                self.sequence, self.transaction = "INACTIVE", "AUCUNE"
        elif action == "intervention":
            self.defauts_leves = self.intervention = self.references = self.bras_sur = True
        elif action == "defaut":
            self.defauts_leves = False
        elif action == "reference-invalide":
            self.references = False
        elif action.startswith("rearmement-"):
            self.mode_rearmement = {"rearmement-ok": "ok", "rearmement-refuse": "refuse",
                                    "rearmement-muet": "muet"}[action]

    def actualiser(self):
        if self.scenario and self.scenario.exists():
            try:
                contenu = json.loads(self.scenario.read_text(encoding="utf-8"))
                if contenu["id"] != self._evenement:
                    self.injecter(contenu["action"])
                    self._evenement = contenu["id"]
            except (ValueError, KeyError, OSError) as erreur:
                self.dernier_evenement = f"SCENARIO INVALIDE : {erreur}"

    def diagnostic(self):
        return {**asdict(self.conditions()), "sequence": self.sequence,
                "nouvelles_autorisees": self.nouvelles, "demarrages_simules": self.demarrages,
                "arrets_demandes": self.arrets, "rearmements_demandes": self.rearmements,
                "annulations": self.annulations, "dernier_evenement": self.dernier_evenement,
                "mode_rearmement": self.mode_rearmement}
