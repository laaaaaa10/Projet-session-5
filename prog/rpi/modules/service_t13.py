"""Etat de service T13, journal durable, progression independante du reseau.

Les decisions reposent sur InterfaceServiceT13. Aucun GPIO ni CAN n'est ouvert.
Le journal ne contient pas de soldes et ne modifie aucun fichier de T02.
"""

import json
from pathlib import Path
import sqlite3
import time

from commun.t13.protocole import ACTIONS_SERVICE, reponse, valider_commande
from api.service_t13 import InterfaceServiceT13


class GestionServiceT13:
    def __init__(self, adaptateur: InterfaceServiceT13, journal, *,
                 cible="simulation", horloge=time.monotonic, delai_rearmement=5.0):
        self.adaptateur = adaptateur
        self.horloge, self.delai_rearmement = horloge, delai_rearmement
        self._attente = None
        self._echeance = None
        self._sortie = []
        self._incident = None
        Path(journal).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(journal)
        self.db.execute("PRAGMA synchronous=FULL")
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS contexte (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS commandes (id TEXT PRIMARY KEY, demande TEXT NOT NULL, resultat TEXT NOT NULL)")
            self.db.execute("INSERT OR IGNORE INTO contexte VALUES ('cible', ?)", (cible,))
        if self.db.execute("SELECT valeur FROM contexte WHERE cle='cible'").fetchone()[0] != cible:
            self.db.close()
            raise ValueError("Journal de service associe a un autre broker/prefixe")
        ligne = self.db.execute("SELECT valeur FROM contexte WHERE cle='etat'").fetchone()
        anciennes = [json.loads(d) for d, r in self.db.execute("SELECT demande, resultat FROM commandes")
                     if json.loads(r)["phase"] == "ACCEPTEE"]
        # Aucun EN_SERVICE ni mouvement n'est restaure automatiquement au demarrage.
        self.etat = "ARRET_VERROUILLE" if anciennes or (ligne and ligne[0] == "ARRET_VERROUILLE") else "HORS_SERVICE"
        self.adaptateur.autoriser_nouvelles(False)
        if self.etat == "ARRET_VERROUILLE":
            self.adaptateur.arreter()
        with self.db:
            self._enregistrer_etat()
            for demande in anciennes:
                self._memoriser(demande, "REFUSEE", "REDEMARRAGE_INTERROMPU")
        self._sortie.clear()  # Le PC retrouvera ces resultats avec les memes ID.

    def _enregistrer_etat(self):
        self.db.execute("INSERT OR REPLACE INTO contexte VALUES ('etat', ?)", (self.etat,))

    def _memoriser(self, demande, phase, code, **details):
        resultat = reponse(demande, phase, code, {
            "etat_service": self.etat, "simulation": self.adaptateur.simulation, **details,
        })
        self.db.execute("INSERT OR REPLACE INTO commandes VALUES (?, ?, ?)",
                        (demande["id_commande"], json.dumps(demande, sort_keys=True), json.dumps(resultat)))
        self._enregistrer_etat()
        self._sortie.append(resultat)

    def _vider(self):
        sortie, self._sortie = self._sortie, []
        return sortie

    def _interrompre_attente(self, code):
        if self._attente is not None:
            self._memoriser(self._attente, "REFUSEE", code, interrompue=True)
            self._attente = self._echeance = None

    def traiter(self, demande):
        valider_commande(demande)
        action = demande["commande"]
        if action not in ACTIONS_SERVICE:
            raise ValueError("Commande hors gestion de service")
        ancien = self.db.execute("SELECT demande, resultat FROM commandes WHERE id=?",
                                 (demande["id_commande"],)).fetchone()
        if ancien:
            if json.loads(ancien[0]) != demande:
                return [reponse(demande, "REFUSEE", "CONFLIT_COMMANDE")]
            resultat = json.loads(ancien[1])
            resultat["donnees"]["deja_traitee"] = True
            return [resultat]
        with self.db:
            conditions = self.adaptateur.conditions()
            if action == "ARRET_IMMEDIAT":
                self.etat = "ARRET_VERROUILLE"
                self.adaptateur.autoriser_nouvelles(False)
                self.adaptateur.arreter()
                self._interrompre_attente("INTERROMPUE_PAR_ARRET")
                self._memoriser(demande, "ACCEPTEE", "ARRET_DEMANDE")
                # Termine signifie verrou T13 etabli et arret demande a l'adaptateur.
                # Cela n'atteste jamais une position mecanique mesuree.
                self._memoriser(demande, "TERMINEE", "ARRET_VERROUILLE")
            elif action == "METTRE_HORS_SERVICE":
                if self.etat == "ARRET_VERROUILLE":
                    self._memoriser(demande, "REFUSEE", "ARRET_VERROUILLE")
                elif self._attente:
                    self._memoriser(demande, "REFUSEE", "COMMANDE_EN_COURS")
                else:
                    self.adaptateur.autoriser_nouvelles(False)
                    if conditions.transaction == "CONFIRMEE":
                        self.etat = "MISE_HORS_SERVICE"
                        self._attente = demande
                        self._memoriser(demande, "ACCEPTEE", "TRANSACTION_A_TERMINER")
                    else:
                        self.adaptateur.annuler_non_confirmee()
                        self.etat = "HORS_SERVICE"
                        self._memoriser(demande, "ACCEPTEE", "MISE_HORS_SERVICE_DEMANDEE")
                        self._memoriser(demande, "TERMINEE", "HORS_SERVICE",
                                       retrait_vehicule_requis=conditions.rampe_occupee)
            elif action == "REMETTRE_EN_SERVICE":
                obstacles = conditions.obstacles()
                if self.etat == "ARRET_VERROUILLE":
                    self._memoriser(demande, "REFUSEE", "ARRET_VERROUILLE")
                elif self._attente:
                    self._memoriser(demande, "REFUSEE", "COMMANDE_EN_COURS")
                elif obstacles or conditions.rampe_occupee or conditions.transaction != "AUCUNE":
                    self._memoriser(demande, "REFUSEE", "SYSTEME_NON_PRET", obstacles=obstacles,
                                   rampe_occupee=conditions.rampe_occupee,
                                   transaction=conditions.transaction)
                else:
                    self.etat = "EN_SERVICE"
                    self.adaptateur.autoriser_nouvelles(True)
                    self._memoriser(demande, "ACCEPTEE", "REMISE_EN_SERVICE_DEMANDEE")
                    self._memoriser(demande, "TERMINEE", "EN_SERVICE")
            elif action == "REINITIALISER":
                obstacles = conditions.obstacles(intervention=True)
                if self.etat != "ARRET_VERROUILLE":
                    self._memoriser(demande, "REFUSEE", "ARRET_NON_VERROUILLE")
                elif self._attente:
                    self._memoriser(demande, "REFUSEE", "COMMANDE_EN_COURS")
                elif obstacles:
                    self._memoriser(demande, "REFUSEE", "REARMEMENT_NON_SUR", obstacles=obstacles)
                else:
                    self._attente = demande
                    self._echeance = self.horloge() + self.delai_rearmement
                    self.adaptateur.lancer_rearmement(demande["id_commande"])
                    self._memoriser(demande, "ACCEPTEE", "REARMEMENT_EN_COURS")
        return self._vider()

    def actualiser(self):
        """Toujours appelee, meme sans connexion MQTT."""
        self.adaptateur.actualiser()
        conditions = self.adaptateur.conditions()
        with self.db:
            # Un defaut critique transmis par les modules verrouille egalement T13.
            if not conditions.defauts_leves and self.etat != "ARRET_VERROUILLE":
                self.etat = "ARRET_VERROUILLE"
                self.adaptateur.autoriser_nouvelles(False)
                self.adaptateur.arreter()
                self._interrompre_attente("INTERROMPUE_PAR_DEFAUT")
                self._incident = "DEFAUT_ACTIF"
                self._enregistrer_etat()
            if self._attente is not None:
                demande = self._attente
                if demande["commande"] == "METTRE_HORS_SERVICE":
                    if conditions.transaction == "AUCUNE":
                        self.etat = "HORS_SERVICE"
                        self._memoriser(demande, "TERMINEE", "HORS_SERVICE")
                        self._attente = None
                else:
                    resultat = self.adaptateur.resultat_rearmement(demande["id_commande"])
                    obstacles = conditions.obstacles(intervention=True)
                    if obstacles or resultat is False or self.horloge() >= self._echeance:
                        code = "REARMEMENT_NON_SUR" if obstacles else (
                            "REARMEMENT_REFUSE" if resultat is False else "REARMEMENT_SANS_REPONSE")
                        self.adaptateur.arreter()
                        self._memoriser(demande, "REFUSEE", code, obstacles=obstacles)
                        self._attente = self._echeance = None
                        self._incident = code
                    elif resultat is True:
                        self.etat = "HORS_SERVICE"
                        self.adaptateur.autoriser_nouvelles(False)
                        self._memoriser(demande, "TERMINEE", "HORS_SERVICE")
                        self._attente = self._echeance = None
                        self._incident = None
        return self._vider()

    def instantane(self):
        return {"etat_service": self.etat, "arret_verrouille": self.etat == "ARRET_VERROUILLE",
                "service_simule": self.adaptateur.simulation,
                "diagnostic_service": self.adaptateur.diagnostic(),
                "incident_service": self._incident,
                "commande_service_en_cours": None if self._attente is None else self._attente["id_commande"]}

    def fermer(self):
        self.db.close()
