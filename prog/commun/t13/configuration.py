"""Configuration explicite : aucune adresse de broker propre a l'equipe."""

from dataclasses import dataclass, field
import os
import re

TOPICS_PI = ("etat", "places", "anomalies", "transactions", "commande/reponse", "comptes/reponse")
TOPICS_PC = ("commande", "comptes/commande")


@dataclass(frozen=True)
class ConfigurationMQTT:
    hote: str
    port: int
    prefixe: str
    tls: bool
    utilisateur: str | None = None
    mot_de_passe: str | None = field(default=None, repr=False)
    certificat_ca: str | None = None

    def __post_init__(self):
        if not isinstance(self.hote, str) or not self.hote.strip():
            raise ValueError("Hote MQTT obligatoire")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("Port MQTT invalide")
        if not isinstance(self.prefixe, str) or re.fullmatch(r"esa/Equipe_[1-5]/?", self.prefixe) is None:
            raise ValueError("Prefixe impose : esa/Equipe_N/ avec N entre 1 et 5, casse exacte")
        object.__setattr__(self, "prefixe", self.prefixe.rstrip("/"))
        if type(self.tls) is not bool:
            raise ValueError("TLS doit etre explicitement active ou desactive")
        if self.certificat_ca and not self.tls:
            raise ValueError("Un certificat CA exige TLS")
        if self.mot_de_passe is not None and not self.utilisateur:
            raise ValueError("Le mot de passe exige un utilisateur")

    @classmethod
    def depuis_environnement(cls):
        requis = ("ESA_MQTT_HOTE", "ESA_MQTT_PORT", "ESA_MQTT_PREFIXE", "ESA_MQTT_TLS")
        manquants = [cle for cle in requis if not os.environ.get(cle)]
        if manquants:
            raise ValueError("Configuration manquante : " + ", ".join(manquants))
        if os.environ["ESA_MQTT_TLS"] not in ("0", "1"):
            raise ValueError("ESA_MQTT_TLS attend 0 ou 1")
        return cls(os.environ["ESA_MQTT_HOTE"], int(os.environ["ESA_MQTT_PORT"]),
                   os.environ["ESA_MQTT_PREFIXE"], os.environ["ESA_MQTT_TLS"] == "1",
                   os.environ.get("ESA_MQTT_UTILISATEUR"),
                   os.environ.get("ESA_MQTT_MOT_DE_PASSE"),
                   os.environ.get("ESA_MQTT_CA"))

    def topic(self, nom):
        if nom not in TOPICS_PI + TOPICS_PC:
            raise ValueError("Topic T13 inconnu")
        return f"{self.prefixe}/{nom}"
