# Essai T06 + T07 — Deux nœuds sur le vrai bus CAN (BAS et BORNE)

- **Date :** 2026-11-26
- **Exécuté par :** William MacDonald
- **Résultat global :** 7/7 réussis

## Montage

| STM32 | Firmware | Rôle | Matériel |
|---|---|---|---|
| A | `prog/stm32_bas`, `ESA_NOEUD_BAS` | T06 : IR des deux PCB-03 ; T07 : places 1–7 (+ éclairage niveau 0 pour l'essai, `ESSAI_ECLAIRAGE_BANC 1`) ; faux RPi (`demo`, `hb`, `ecl`) avec écho local des trames | PCB-04 sur MikroBus 1 (PCB-03 du bas) et MikroBus 2 (PCB-03 du milieu) ; PCB-11 → PCB-06 du bas |
| B | `prog/stm32_bas`, `ESA_NOEUD_BORNE` | T07 : places 8–14 + éclairage niveau 1 | PCB-11 → PCB-06 du milieu |

- Bus CAN : bornier P12 des deux PCB-12 relié 1↔1 (CANH), 2↔2 (CANL), 3↔3 (GND) ; cavalier J4 (120 Ω) sur les deux PCB-12. 500 kbit/s, `ESSAI_CAN_LOOPBACK 0`.
- Alimentation des deux PCB-11 : 5,0 V de labo, limite ≈ 2 A.
- Un seul projet pour les deux nœuds : seule la ligne `ESA_NOEUD` de `esa_noeud.h` change (remise à `ESA_NOEUD_BAS` après le flash du STM32 B).

## Résultats (commandes tapées sur la console du BAS)

| # | Essai | Attendu | Verdict |
|---|---|---|---|
| 1 | `trace on` | HEARTBEAT_BORNE (0x043) toutes les 500 ms | Réussi |
| 2 | `ir` | 2 cartes, 0 erreur I2C, état VALIDE (14 places connues) | Réussi |
| 3 | `demo on`, voitures déplacées sur les deux cartes | Témoins vert / rouge sous les voitures sur les deux cartes ; réponses 0x342 APPLIQUE de la BORNE pour les places 8–14 ; table de la carte du milieu (circuit k → place 14 − k) confirmée | Réussi |
| 4 | `demo reserve 10`, `demo reparation 12` | Place 10 bleue (rouge si occupée), place 12 jaune | Réussi |
| 5 | `ecl 0 blanc 40`, `ecl 1 chaud 40` | Éclairage sous la carte du bas (BAS), puis sous la carte du milieu (BORNE, réponse 0x351 APPLIQUE) | Réussi |
| 6 | `hb on`, 2 s, `hb off`, puis `hb on` et `demo on` | Après ≈ 1,5 s : témoins des deux cartes en jaune clignotant, éclairage conservé ; retour des couleurs quand le faux RPi retransmet | Réussi |
| 7 | `demo off` | Témoins et éclairage éteints sur les deux cartes | Réussi |

## À retenir

- La table IR de la carte du milieu est la même que celle du bas (sens inverse des DEL), sur la PCB-04 du MikroBus 2.
- Pour la maquette : `ESSAI_ECLAIRAGE_BANC 0` (le BAS n'a pas d'éclairage), et le faux RPi sera remplacé par le vrai RPi (`ESSAI_FAUX_RPI` vaut 1 seulement sur le BAS, pour les essais).
- Reste : essai avec le vrai RPi (délais de réponse ≤ 500 ms pour T07, ≤ 250 ms pour T06), STM32 HAUT (éclairage niveau 2, détecteur d'entrée 0x310/0x311), numérotation officielle des places (E1.1…) à confirmer avec l'équipe.
