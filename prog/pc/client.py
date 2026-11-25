"""Client de supervision sans interface graphique. A executer hors du thread GUI."""

import time
import re

from commun.t13.protocole import canal_commande, canal_reponse, decoder, nouvelle_commande, valider_reponse


def valider_etat(etat):
    if (not isinstance(etat, dict) or type(etat.get("version")) is not int or etat["version"] != 1
            or not isinstance(etat.get("session"), str) or not etat["session"]
            or type(etat.get("revision")) is not int or etat["revision"] < 1
            or etat.get("source") != "PI" or not isinstance(etat.get("etat_service"), str)
            or type(etat.get("disponibilite")) is not dict
            or any(type(v) is not bool for v in etat["disponibilite"].values())
            or type(etat.get("anomalies")) is not list):
        raise ValueError("Instantane invalide")
    places = etat.get("places")
    if (not isinstance(places, list) or len(places) != 14
            or any(type(p) is not dict or not isinstance(p.get("id"), str)
                   or not isinstance(p.get("logique"), str) for p in places)
            or {p["id"] for p in places} != {f"E{e}.{p}" for e in (1, 2) for p in range(1, 8)}):
        raise ValueError("Les 14 places doivent etre explicites")
    soldes = etat.get("soldes")
    if soldes is not None and (type(soldes) is not dict
                              or any(re.fullmatch(r"[0-9A-F]{10}", k) is None
                                     or type(v) is not int or v < 0 for k, v in soldes.items())):
        raise ValueError("Soldes invalides")
    return etat


class ClientSupervision:
    def __init__(self, transport, journal, *, horloge=time.monotonic, peremption=15, repetition=3):
        self.transport, self.journal, self.horloge = transport, journal, horloge
        self.peremption, self.repetition = peremption, repetition
        self.etat = None
        self._generation = 0
        self._synchronise = False
        self._derniere = float("-inf")
        self._sync = None
        self._sync_envoi = float("-inf")
        self._envois = {}
        self._fragments = {}
        self.messages_invalides = 0

    @property
    def frais(self):
        return (self.transport.etat[0] and self._synchronise
                and self.horloge() - self._derniere < self.peremption)

    def demander(self, action, **parametres):
        if not self.frais:
            raise ValueError("Attendre une resynchronisation avec le Pi")
        if action == "AJOUTER_CREDIT" and any(
            d["commande"] == action and d["parametres"]["id_uart"] == parametres.get("id_uart")
            for d in self.journal.en_attente()
        ):
            raise ValueError("Un credit reste en attente pour cette carte ; reprendre son ID")
        demande = nouvelle_commande(action, **parametres)
        self.journal.ajouter(demande)  # Commit durable avant tout envoi.
        return demande["id_commande"]

    def reprendre(self, identifiant):
        self.journal.reprendre(identifiant)
        self._envois.pop(identifiant, None)

    def _invalider(self):
        self._synchronise = False
        self._derniere = float("-inf")
        self._fragments.clear()

    def _recevoir_etat(self, nom, donnees, retenu):
        if (type(donnees.get("version")) is not int or donnees["version"] != 1
                or not isinstance(donnees.get("session"), str) or not donnees["session"]
                or len(donnees["session"]) > 128 or type(donnees.get("revision")) is not int
                or donnees["revision"] < 1 or donnees.get("source") != "PI"):
            raise ValueError("Fragment d'etat invalide")
        cle = (donnees["session"], donnees["revision"])
        fragments = self._fragments.setdefault(cle, {})
        fragments[nom] = (donnees, retenu)
        while len(self._fragments) > 4:
            del self._fragments[next(iter(self._fragments))]
        if set(fragments) != {"etat", "places", "anomalies", "transactions"}:
            return
        etat = dict(fragments["etat"][0])
        for champ in ("places", "anomalies", "transactions"):
            if champ not in fragments[champ][0]:
                raise ValueError("Fragment incomplet")
            etat[champ] = fragments[champ][0][champ]
        valider_etat(etat)
        ancien = any(r for _, r in fragments.values())
        del self._fragments[cle]
        if self.etat is None:
            self.etat = etat
        elif not ancien and self._synchronise:
            if etat["session"] != self.etat["session"]:
                self._invalider()
            elif etat["revision"] > self.etat["revision"]:
                self.etat, self._derniere = etat, self.horloge()

    def _recevoir(self, message):
        config = self.transport.config
        try:
            donnees = decoder(message.payload)
            if message.topic == config.topic("etat") and donnees.get("type") == "disponibilite":
                if donnees.get("version") == 1 and donnees.get("en_ligne") is False:
                    self._invalider()
                return
            for nom in ("etat", "places", "anomalies", "transactions"):
                if message.topic == config.topic(nom):
                    self._recevoir_etat(nom, donnees, message.retenu)
                    return
            if message.topic not in {config.topic("commande/reponse"), config.topic("comptes/reponse")} or message.retenu:
                return
            resultat = valider_reponse(donnees)
            if message.topic != config.topic(canal_reponse(resultat["commande"])):
                raise ValueError("Reponse sur le mauvais topic")
            if self._sync is not None and resultat["id_commande"] == self._sync["id_commande"]:
                if (resultat["commande"] == "SYNCHRONISER" and resultat["phase"] == "TERMINEE"
                        and resultat["code"] == "SYNCHRONISE"):
                    self.etat = valider_etat(resultat["donnees"].get("etat"))
                    self._synchronise, self._derniere = True, self.horloge()
                    self._sync = None
                return
            demande = self.journal.demande(resultat["id_commande"])
            if demande is not None and resultat["commande"] == demande["commande"]:
                if demande["commande"] == "AJOUTER_CREDIT" and resultat["phase"] == "TERMINEE":
                    recu = resultat["donnees"].get("recu")
                    params = demande["parametres"]
                    if (type(recu) is not dict or recu.get("id_transaction") != demande["id_commande"]
                            or recu.get("id_uart") != params["id_uart"]
                            or type(recu.get("montant_centimes")) is not int
                            or recu["montant_centimes"] != params["montant_centimes"]
                            or recu.get("type_operation") != "CREDIT"
                            or recu.get("statut") != resultat["code"]
                            or resultat["code"] not in {"CREDITE", "COMPTE_INCONNU"}
                            or type(recu.get("deja_traitee")) is not bool):
                        raise ValueError("Recu de credit incompatible avec la demande")
                self.journal.enregistrer_reponse(resultat)
        except (ValueError, TypeError):
            self.messages_invalides += 1

    def actualiser(self):
        connecte, generation, _ = self.transport.etat
        if not connecte:
            self._invalider()
            return
        if generation != self._generation:
            self._generation = generation
            self._invalider()
            self._sync = None
            self._sync_envoi = float("-inf")
            self._envois.clear()
        for message in self.transport.recevoir(maximum=32):
            self._recevoir(message)
        maintenant = self.horloge()
        if not self.frais:
            if self._sync is None:
                self._sync = nouvelle_commande("SYNCHRONISER")
                self._sync_envoi = float("-inf")
            if maintenant - self._sync_envoi >= self.repetition:
                self.transport.publier(canal_commande(self._sync["commande"]), self._sync)
                self._sync_envoi = maintenant
            return
        # Huit maximum par passage. Pas de nouvelle reference lors d'un retry.
        nombre = 0
        for demande in self.journal.en_attente():
            identifiant = demande["id_commande"]
            if maintenant - self._envois.get(identifiant, float("-inf")) >= self.repetition:
                if self.transport.publier(canal_commande(demande["commande"]), demande):
                    self._envois[identifiant] = maintenant
                nombre += 1
                if nombre >= 8:
                    break

    def vue(self):
        connecte, _, incident = self.transport.etat
        statut = "A_JOUR" if self.frais else ("PERIMEES" if connecte else "DECONNECTE")
        return {"statut": statut, "incident": incident, "etat": self.etat,
                "demandes": self.journal.historique()}

    def fermer(self):
        try:
            self.transport.fermer()
        finally:
            self.journal.fermer()
