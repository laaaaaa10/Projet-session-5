"""Raspberry Pi 5 de la borne - Programme principal."""

# --- Imports ---------------------------------------------------------------
from communications import can_bus
from communications import mqtt_client
from interface import ecran_tactile
from modules import barriere
from modules import lecteur_code_barres
from modules import lecteur_nfc_rfid
from modules import radar_presence

# TODO : initialiser le bus CAN et le client MQTT
# TODO : initialiser les modules (barrière, lecteurs, radar) et l'écran tactile
# TODO : boucle principale
