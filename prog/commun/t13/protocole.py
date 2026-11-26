"""Champs JSON proposes ; id_commande et topics imposes par l'interface T13."""

import json
import re
from uuid import uuid4

VERSION = 1
TAILLE_MAX = 65536
ACTIONS_SERVICE = frozenset({"METTRE_HORS_SERVICE", "REMETTRE_EN_SERVICE",
                            "ARRET_IMMEDIAT", "REINITIALISER"})
ACTIONS_COMPTES = frozenset({"CONSULTER_SOLDE", "AJOUTER_CREDIT"})
# Extension technique proposee pour un echange de resynchronisation identifie.
ACTIONS = ACTIONS_SERVICE | ACTIONS_COMPTES | {"SYNCHRONISER"}
PHASES = {"ACCEPTEE", "TERMINEE", "REFUSEE", "INCERTAINE"}


def canal_commande(action):
    return "comptes/commande" if action in ACTIONS_COMPTES else "commande"


def canal_reponse(action):
    return "comptes/reponse" if action in ACTIONS_COMPTES else "commande/reponse"


def repartir_etat(etat):
    """Quatre publications de meme session/revision, sans melange de generations."""
    commun = {cle: etat[cle] for cle in ("version", "session", "revision", "source")}
    general = {cle: valeur for cle, valeur in etat.items() if cle not in {"places", "anomalies", "transactions"}}
    return {"etat": general, **{nom: {**commun, nom: etat[nom]}
                              for nom in ("places", "anomalies", "transactions")}}


def encoder(valeur):
    return json.dumps(valeur, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _objet_unique(paires):
    resultat = {}
    for cle, valeur in paires:
        if cle in resultat:
            raise ValueError("Cle JSON repetee")
        resultat[cle] = valeur
    return resultat


def _refuser_constante(_):
    raise ValueError("Nombre JSON invalide")


def decoder(payload):
    if len(payload) > TAILLE_MAX:
        raise ValueError("Message trop volumineux")
    try:
        valeur = json.loads(payload, object_pairs_hook=_objet_unique, parse_constant=_refuser_constante)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as erreur:
        raise ValueError("JSON invalide") from erreur
    if type(valeur) is not dict:
        raise ValueError("Objet JSON attendu")
    return valeur


def id_valide(valeur):
    return isinstance(valeur, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", valeur) is not None


def valider_commande(message):
    if set(message) != {"version", "id_commande", "commande", "parametres"}:
        raise ValueError("Champs de commande invalides")
    if type(message["version"]) is not int or message["version"] != VERSION:
        raise ValueError("Version inconnue")
    if not id_valide(message["id_commande"]):
        raise ValueError("ID de demande invalide")
    action, params = message["commande"], message["parametres"]
    if not isinstance(action, str) or action not in ACTIONS or type(params) is not dict:
        raise ValueError("Commande ou parametres invalides")
    attendus = {"id_uart"} if action == "CONSULTER_SOLDE" else set()
    if action == "AJOUTER_CREDIT":
        attendus = {"id_uart", "montant_centimes"}
        if not message["id_commande"].startswith("t13:credit-"):
            raise ValueError("Un credit exige un ID durable prefixe t13:credit-")
        if type(params.get("montant_centimes")) is not int or params["montant_centimes"] <= 0:
            raise ValueError("Credit : entier strictement positif en centimes requis")
    if set(params) != attendus:
        raise ValueError("Parametres manquants ou inconnus")
    if "id_uart" in params and (not isinstance(params["id_uart"], str)
                               or re.fullmatch(r"[0-9A-F]{10}", params["id_uart"]) is None):
        raise ValueError("ID UART complet de dix caracteres hexadecimaux majuscules requis")
    return message


def nouvelle_commande(action, **parametres):
    prefixe = "t13:credit-" if action == "AJOUTER_CREDIT" else "t13:demande-"
    return valider_commande({"version": VERSION, "id_commande": prefixe + uuid4().hex,
                            "commande": action, "parametres": parametres})


def reponse(commande, phase, code, donnees=None):
    return {"version": VERSION, "id_commande": commande["id_commande"],
            "commande": commande["commande"], "phase": phase, "code": code,
            "donnees": donnees or {}}


def valider_reponse(message):
    if (set(message) != {"version", "id_commande", "commande", "phase", "code", "donnees"}
            or type(message["version"]) is not int or message["version"] != VERSION
            or not id_valide(message["id_commande"])
            or not isinstance(message["commande"], str) or len(message["commande"]) > 128
            or not isinstance(message["phase"], str) or message["phase"] not in PHASES
            or not isinstance(message["code"], str) or type(message["donnees"]) is not dict):
        raise ValueError("Reponse invalide")
    return message
