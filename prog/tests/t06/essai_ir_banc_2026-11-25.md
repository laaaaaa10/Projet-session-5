# Essai T06 — Détection IR sur le banc (PCB-03 du bas, une PCB-04)

- **Dates :** 2026-11-25 et 2026-11-26
- **Exécuté par :** William MacDonald
- **Matériel :** STM32F407 Discovery sur PCB-12 RevA ; PCB-04 (mode PWM, TCA6416A à 0x20) sur le MikroBus 1 ; PCB-06 ; PCB-03 du bas reliée par les deux câbles Micro-Fit (PCB-06 J2 → PCB-03 J1 et PCB-06 J5 → PCB-03 J2) ; PCB-11 sur P8 pour les DEL (5 V de labo).
- **Logiciel :** `prog/stm32_bas`, `ESSAI_BALAYAGE_DEL 0`, `ESSAI_CAN_LOOPBACK 1`, `ESSAI_NB_CARTES_IR 1`.

## Câblage PCB-04 → PCB-06

| PCB-04 J1 (récepteurs) | PCB-06 | PCB-04 J2 (émetteurs) | PCB-06 |
|---|---|---|---|
| 1 (P0.0) | J3-3 IR_IN1 | 1 (S0) | J6-1 IR_PWM1 |
| 2 (P0.1) | J3-2 IR_IN2 | 2 (S1) | J4-6 IR_PWM2 |
| 3 (P0.2) | J3-1 IR_IN3 | 3 (S2) | J4-5 IR_PWM3 |
| 4 (P0.3) | J1-6 IR_IN4 | 4 (S3) | J4-4 IR_PWM4 |
| 5 (P0.4) | J1-5 IR_IN5 | 5 (S4) | J4-3 IR_PWM5 |
| 6 (P0.5) | J1-4 IR_IN6 | 6 (S5) | J4-2 IR_PWM6 |
| 7 (P0.6) | J1-3 IR_IN7 | 7 (S6) | J4-1 IR_PWM7 |
| 8 (P0.7) | J1-2 IR_IN8 | 8 (S7) | J3-6 IR_PWM8 |
| 9 (3,3 V) | J3-4 P3V3 | 9 (3,3 V) | non branché |
| 10 (GND) | J3-5 GND | 10 (GND) | J1-1 GND |

Le 3,3 V des circuits IR passe par le câble PCB-06 J2 → PCB-03 J1 (broches 9-10) : les deux câbles Micro-Fit sont nécessaires.

## Résultats

| # | Vérification | Attendu | Obtenu | Verdict |
|---|---|---|---|---|
| 1 | 3,3 V sur la PCB-03 (pastilles « 3V3 » et « GND ») | ≈ 3,3 V | 3 V à la PCB-06 ; 60 mV à la PCB-03 tant que le câble J2 → J1 manquait, correct une fois branché | Réussi |
| 2 | PCB-04 joignable | 0 erreur I2C | 0 erreur, 0 parasite | Réussi |
| 3 | Lecture sans émetteur (`ir brut`, « aucun emetteur ») | Aucun récepteur actif | `........` | Réussi |
| 4 | Sens de détection | À déterminer | Place vide : le récepteur k voit l'émetteur k → **barrière, faisceau coupé = présence** (`T06_PRESENCE_SI_PORTEUSE 0`) | Réussi |
| 5 | Voitures sur deux places | 2 places en présence, les autres en absence | Conforme | Réussi |
| 6 | Correspondance circuit ↔ place | À relever | Sens inverse des DEL : circuit k → place 7 − k (k = 0 à 6), circuit 7 = passage du bras (entrée) | Réussi |
| 7 | `demo on` (faux RPi en loopback) : rouge sous les voitures, vert ailleurs | Les 7 places suivent la voiture | Conforme sur les 7 places | Réussi |
| 8 | RESET pendant le balayage | La PCB-04 répond encore sans débrancher l'USB | Conforme après l'ajout du déblocage du bus I2C | Réussi |

## Problèmes rencontrés

- **Bus I2C bloqué après un flash ou un RESET** : le TCA6416A, resté alimenté, gardait SDA à 0 → toutes les lectures échouaient. Corrigé dans `t06_pcb04.c` (9 impulsions SCL, STOP, remise à zéro du périphérique I2C, réinitialisation automatique après 3 échecs).
- **Quatre fichiers non mis à jour sur le disque** lors d'un envoi : le programme flashé était encore l'ancien (sens inversé). Vérification ajoutée : relire les fichiers après chaque envoi.

## Reste à vérifier

- Deuxième PCB-04 sur le MikroBus 2 avec la PCB-03 du milieu (places 8 à 14) : même table supposée.
- Délai de confirmation mesuré sur le matériel (tests PC : pire cas 101 ms pour 250 ms exigés).
- Passage du bras (circuit 7) avec un objet dans l'entrée.
- Essai sur le vrai bus CAN avec le RPi (0x300, 0x301, 0x302, 0x080).
