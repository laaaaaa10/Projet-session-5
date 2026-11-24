# Essai T07 — STM32 BAS seul, CAN en loopback

- **Date :** 2026-11-24
- **Exécuté par :** William MacDonald
- **Matériel :** STM32F407 Discovery seule, sans PCB-12, sans PCB-11 ni transceiver CAN. Console par USB CDC (micro-USB) dans PuTTY.
- **Logiciel :** `prog/stm32_bas`, `ESSAI_CAN_LOOPBACK 1`, `ESSAI_BALAYAGE_DEL 0`.
- **Principe :** en loopback, le contrôleur CAN reçoit ses propres trames. Chaque commande tapée passe donc par le vrai contrôleur CAN, puis par `noeud.c`, puis par `t07_del.c`, qui répond sur le CAN.
- **Limite :** les DEL elles-mêmes ne sont pas observées, faute de PCB-11. On vérifie l'image envoyée au SPI (commande `image`).

## Résultats

| # | Commande | Attendu | Obtenu | Verdict |
|---|---|---|---|---|
| 1 | `del 3 255 0 0` | 0x341 [seq, 3, 1] APPLIQUE ; DEL 5 rouge | `<- 0x341 … place=3 -> APPLIQUE` ; `image` : DEL 5 = 255,0,0 | Réussi |
| 2 | `del 9 0 255 0` | Aucune réponse (place du HAUT) | Aucune réponse | Réussi |
| 3 | `del 15 1 1 1` | REFUSE (place hors plage) | `place=15 -> REFUSE` | Réussi |
| 4 | `del 3 1 1 1 2` | REFUSE (mode 2) ; place 3 inchangée | `place=3 -> REFUSE` ; DEL 5 toujours 255,0,0 | Réussi |
| 5 | `brut 340 05 03 ff 00 00` | REFUSE (DLC 5) | `place=3 -> REFUSE` | Réussi |
| 6 | `ecl 0 200 200 200` | 0x350 APPLIQUE ; 8 DEL d'indice pair à 200,200,200 | `niveau=0 -> APPLIQUE` ; `image` : DEL 0, 2, …, 14 = 200,200,200 | Réussi |
| 7 | `ecl 1 9 9 9` | Aucune réponse (niveau du HAUT) | Aucune réponse | Réussi |
| 8 | `ecl 3 9 9 9` | REFUSE (niveau hors plage) | `niveau=3 -> REFUSE` | Réussi |
| 9 | `del 2 255 255 0 1`, puis `image` ×3 | DEL 3 alterne entre éteinte et jaune | DEL 3 : 0,0,0 ; 0,0,0 ; 255,255,0 | Réussi (alternance observée ; durée non mesurée) |
| 10 | `hb on`, `hb off`, `hb on`, `etat` | Perte détectée : 7 places INCONNUE ; RPi de nouveau EN LIGNE ; éclairage conservé | `RPi : EN LIGNE` ; places 1 à 7 INCONNUE ; éclairage 200,200,200 | Réussi |
| 11 | `del 3 255 0 0` après le retour du RPi | Place 3 redevient valide, les autres restent INCONNUE | Non exécuté (faute de frappe : `de 3 …`) | À refaire |
| 12 | RESET, puis `etat` | Places « initiale », éclairage 64,64,64 | Non exécuté | À faire |

**Compteurs à la fin :**
- T07 : 3 appliquées, 4 refusées, 2 ignorées, 0 réponse non envoyée. Cohérent avec les essais 1 à 10.
- CAN : 927 trames reçues pour 927 envoyées ; 0 perdue en réception, 0 refusée ou annulée en émission.

## Journal brut (PuTTY)

```
=== Essai T07 (STM32 BAS) ===
CAN en loopback. Taper aide.
del 3 255 0 0
-> 0x340 DEL_PLACE_CMD        DLC 6 : 00 03 FF 00 00 00
<- 0x341 DEL_BAS_ETAT : seq=0 place=3 -> APPLIQUE
del 9 0 255 0
-> 0x340 DEL_PLACE_CMD        DLC 6 : 01 09 00 FF 00 00
del 15 1 1 1
-> 0x340 DEL_PLACE_CMD        DLC 6 : 02 0F 01 01 01 00
<- 0x341 DEL_BAS_ETAT : seq=2 place=15 -> REFUSE
del 3 1 1 1 2
-> 0x340 DEL_PLACE_CMD        DLC 6 : 03 03 01 01 01 02
<- 0x341 DEL_BAS_ETAT : seq=3 place=3 -> REFUSE
brut 340 05 03 ff 00 00
-> 0x340 DEL_PLACE_CMD        DLC 5 : 05 03 FF 00 00
<- 0x341 DEL_BAS_ETAT : seq=5 place=3 -> REFUSE
ecl 0 200 200 200
-> 0x130 ECLAIRAGE_CMD        DLC 5 : 04 00 C8 C8 C8
<- 0x350 ECLAIRAGE_BAS_ETAT : seq=4 niveau=0 -> APPLIQUE
ecl 1 9 9 9
-> 0x130 ECLAIRAGE_CMD        DLC 5 : 05 01 09 09 09
ecl 3 9 9 9
-> 0x130 ECLAIRAGE_CMD        DLC 5 : 06 03 09 09 09
<- 0x350 ECLAIRAGE_BAS_ETAT : seq=6 niveau=3 -> REFUSE
del 2 255 255 0 1
-> 0x340 DEL_PLACE_CMD        DLC 6 : 07 02 FF FF 00 01
<- 0x341 DEL_BAS_ETAT : seq=7 place=2 -> APPLIQUE
image   (3 fois ; DEL 3 : éteinte, éteinte, 255,255,0 ; DEL 5 : 255,0,0 ; indices pairs : 200,200,200)
hb on / hb off / hb on
etat
RPi : EN LIGNE | heartbeat simule : oui | CAN loopback
  place  1 (DEL  1) : INCONNUE  R=  0 V=  0 B=  0  fixe
  place  2 (DEL  3) : INCONNUE  R=255 V=255 B=  0  clignote
  place  3 (DEL  5) : INCONNUE  R=255 V=  0 B=  0  fixe
  place  4 (DEL  7) : INCONNUE  R=  0 V=  0 B=  0  fixe
  place  5 (DEL  9) : INCONNUE  R=  0 V=  0 B=  0  fixe
  place  6 (DEL 11) : INCONNUE  R=  0 V=  0 B=  0  fixe
  place  7 (DEL 13) : INCONNUE  R=  0 V=  0 B=  0  fixe
  eclairage niveau 0 : R=200 V=200 B=200
T07 : 3 appliquees, 4 refusees, 2 ignorees, 0 reponses non envoyees
CAN : 927 recues, 927 envoyees, 0 perdues RX, 0 refusees TX, 0 annulees TX
```

## Reste à vérifier

- Essais 11 et 12 ci-dessus.
- Délai de réponse ≤ 500 ms : non mesuré. À mesurer sur le vrai bus, avec l'analyseur logique ou les horodatages du RPi.
- DEL réelles (couleurs, positions, clignotement à l'œil, 5 V au blanc maximal) : dès que le PCB-11 sera reçu (balayage `ESSAI_BALAYAGE_DEL 1`).
