"""
essai_billet_can.py - T05 (RPi) : demande d'impression d'un billet par CAN.

Envoie IMPRESSION_CMD (0x360) et IMPRESSION_DATE (0x361) au STM32 Borne,
puis attend et affiche les réponses IMPRESSION_ETAT (0x230).

Usage : python3 essai_billet_can.py [transaction] [place]
        ex. python3 essai_billet_can.py 123456 12

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T05)
"""
import struct
import sys
import time
from datetime import datetime

import can

# --- Identifiants CAN (protocole v1.6) --------------------------------------
ID_IMPRESSION_CMD = 0x360
ID_IMPRESSION_DATE = 0x361
ID_IMPRESSION_ETAT = 0x230

# --- DB1 et DB2 de 0x230 ----------------------------------------------------
RESULTATS = {0: "refusée", 1: "données validées", 2: "envoyée sur UART", 3: "erreur"}
ERREURS = {
    0x00: "aucune", 0x01: "DLC invalide", 0x02: "type invalide",
    0x03: "transaction hors plage", 0x04: "place invalide", 0x05: "date invalide",
    0x06: "trame manquante", 0x07: "imprimante occupée", 0x08: "erreur UART",
    0x09: "délai UART dépassé", 0x0B: "incohérence",
}

DELAI_REPONSE_S = 5.0   # attente maximale de la réponse finale


def main():
    transaction = int(sys.argv[1]) if len(sys.argv) > 1 else 4213
    place = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    sequence = int(time.time()) % 256          # nouvelle séquence à chaque essai
    maintenant = datetime.now()                 # horodatage fourni par le RPi

    bus = can.Bus(interface="socketcan", channel="can0")

    # '<' little-endian, 'B' uint8, 'I' uint32
    donnees_cmd = struct.pack("<BBIBB", sequence, 0x01, transaction, place, 0)
    donnees_date = struct.pack("<7B", sequence, maintenant.year - 2000,
                               maintenant.month, maintenant.day, maintenant.hour,
                               maintenant.minute, maintenant.second)

    # Les deux trames sont envoyées immédiatement l'une après l'autre (< 1 s)
    bus.send(can.Message(arbitration_id=ID_IMPRESSION_CMD, data=donnees_cmd,
                         is_extended_id=False))
    bus.send(can.Message(arbitration_id=ID_IMPRESSION_DATE, data=donnees_date,
                         is_extended_id=False))
    print(f"Demande envoyée : séquence {sequence}, transaction {transaction:06d}, "
          f"place {place}, {maintenant:%Y-%m-%d %H:%M:%S}")

    # Attente des réponses 0x230 portant NOTRE séquence
    limite = time.monotonic() + DELAI_REPONSE_S
    termine = False
    while time.monotonic() < limite:
        msg = bus.recv(timeout=0.5)
        if msg is None or msg.arbitration_id != ID_IMPRESSION_ETAT or msg.dlc != 3:
            continue
        seq, resultat, erreur = msg.data[0], msg.data[1], msg.data[2]
        if seq != sequence:
            continue   # réponse à une autre demande
        print(f"  0x230 : {RESULTATS.get(resultat, '?')} "
              f"(erreur : {ERREURS.get(erreur, hex(erreur))})")
        if resultat in (0, 2, 3):   # réponse finale
            termine = True
            break

    if not termine:
        print("  Aucune réponse finale reçue : vérifier le bus et le STM32 Borne")
    # Le numéro est TOUJOURS affiché, même si l'impression échoue
    print(f"Numéro de transaction : {transaction:06d}")

    bus.shutdown()


if __name__ == "__main__":
    main()