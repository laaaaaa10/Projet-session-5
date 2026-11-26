"""Branchement optionnel T13. N'ouvre ni lecteur ni QWidget."""

import os
from pathlib import Path
import sys

from api.comptes import InterfaceComptes, ModuleT13


def creer_module_t13(comptes: InterfaceComptes) -> ModuleT13 | None:
    """Activer explicitement avec ESA_T13_ACTIVER=1 et les parametres MQTT."""
    if os.environ.get("ESA_T13_ACTIVER", "0") == "0":
        return None
    if os.environ["ESA_T13_ACTIVER"] != "1":
        raise ValueError("ESA_T13_ACTIVER attend 0 ou 1")
    prog = str(Path(__file__).resolve().parents[2])
    if prog not in sys.path:
        sys.path.insert(0, prog)
    from commun.t13.configuration import ConfigurationMQTT
    from communications.mqtt_client import TransportMQTT
    from modules.supervision import SupervisionT13
    transport = TransportMQTT(ConfigurationMQTT.depuis_environnement(), "pi")
    module = SupervisionT13(comptes, transport)
    transport.demarrer()
    return module
