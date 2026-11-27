# Essai T06 + T07 — Trois nœuds sur le vrai bus CAN, disco et commandes d'essai

- **Date :** 2026-11-26
- **Exécuté par :** William MacDonald (verdicts selon ses observations au banc)
- **Suite de :** `prog/tests/t06/essai_t06_t07_deux_noeuds_2026-11-26.md`
- **Résultat global :** 6/6 réussis

## Montage

| STM32 | Firmware | Rôle | Matériel |
|---|---|---|---|
| A | `prog/stm32_bas`, `ESA_NOEUD_BAS` | T06 (IR des deux PCB-03) ; T07 places 1–7 (+ éclairage niveau 0 pour l'essai, `ESSAI_ECLAIRAGE_BANC 1`) ; faux RPi | PCB-04 sur MikroBus 1 et 2 ; PCB-11 → PCB-06 du bas |
| B | `prog/stm32_bas`, `ESA_NOEUD_BORNE` | T07 places 8–14 + éclairage niveau 1 | PCB-11 → PCB-06 du milieu |
| C | `prog/stm32_bas`, `ESA_NOEUD_HAUT` | T07 éclairage niveau 2 (dessous) + ambiance des parkings (témoins du dessus) | PCB-11 → PCB-06 → PCB-03 du haut |

- Bus CAN comme à l'essai à deux nœuds (bornier P12, 500 kbit/s) ; cavalier J4 (120 Ω) seulement sur les deux PCB-12 aux bouts du bus.
- Un seul projet pour les trois nœuds : seule la ligne `ESA_NOEUD` de `esa_noeud.h` change ; remise à `ESA_NOEUD_BAS` pour le dépôt.
- Flasher avec **un seul ST-LINK branché** : avec plusieurs cartes branchées, CubeIDE peut programmer une autre carte que celle visée (un message de l'ancienne version a été vu après un flash pendant l'essai).

## Résultats

| # | Essai | Attendu | Verdict |
|---|---|---|---|
| 1 | Trois nœuds ensemble ; `ecl 2 …` depuis le BAS | Le HAUT allume l'éclairage du niveau 2 et répond 0x352 ; BAS et BORNE fonctionnent comme à l'essai à deux nœuds | Réussi |
| 2 | Démarrage du HAUT | Dessous blanc modéré (64, 64, 64), parkings rouges (64, 0, 0) ; `etat` affiche la ligne « ambiance parkings » | Réussi |
| 3 | `ecl parkings <couleur> [%]` | Seuls les 7 témoins du dessus du HAUT changent ; le dessous reste blanc | Réussi |
| 4 | `disco <1\|2\|3> [cible] [tout\|parkings\|dessous] [%]`, `disco off` | Arc-en-ciel, stroboscope, poursuite sur la zone choisie ; avec la zone parkings, le dessous reste allumé ; à l'arrêt, l'image normale revient | Réussi |
| 5 | `ecl tous blanc 10` | Niveaux 0, 1 et 2 en blanc faible (réponses 0x350, 0x351, 0x352) ; parkings du haut et disco des parkings non touchés | Réussi |
| 6 | `demo intensite <place\|tous> <%>`, puis `demo on` | Témoins atténués (une place ou les 14) ; `demo on` remet l'état initial sans RESET : disco arrêtée, éclairage blanc, parkings du haut rouges, places normales à 100 % | Réussi |

## Trames d'essai (hors protocole v1.6)

| ID | Nom | DLC | Contenu |
|---|---|---|---|
| 0x7F0 | ESSAI_DISCO | 3 ou 4 | mode (0 arrêt, 1 arc-en-ciel, 2 stroboscope, 3 poursuite), cible (1 BAS, 2 HAUT, 3 BORNE, 0xFF tous), intensité %, zone (0 tout, 1 parkings, 2 dessous ; facultative) |
| 0x7F1 | ESSAI_AMBIANCE | 3 | R, V, B des parkings du HAUT |

Ces trames servent seulement aux essais. Pour que le vrai RPi les utilise, il faudrait les ajouter au protocole (décision de l'équipe et de l'enseignant).

## Tests sur PC

- `prog/tests/t07` : T07 89/89 (ambiance, surcouche), disco 40/40 (zones), pilote 31/31, nœud 13/13.
- Console vérifiée à part (harnais hors dépôt) : `ecl tous` 18/18, démo du faux RPi 50/50.
- Les trois versions (BAS, BORNE, HAUT) compilent pour l'ARM sans avertissement.

## À retenir

- Pour la maquette : `ESSAI_ECLAIRAGE_BANC 0` ; le faux RPi (BAS seulement) sera remplacé par le vrai RPi.
- Reste : essai avec le vrai RPi (≤ 500 ms pour T07, ≤ 250 ms pour T06), détecteur d'entrée du HAUT (0x310/0x311), numérotation officielle des places à confirmer avec l'équipe, message à l'équipe sur l'écart au protocole (répartition des DEL) et sur les trames d'essai 0x7F0/0x7F1.
