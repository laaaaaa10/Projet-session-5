# Essai T07 — DEL réelles (PCB-08 et PCB-03) avec le STM32 BAS

- **Date :** 2026-11-25
- **Exécuté par :** William MacDonald
- **Matériel :** STM32F407 Discovery sur PCB-12 RevA ; PCB-11 sur P8 (PMOD SPI) ; PCB-08 ; PCB-06 + câble Micro-Fit 12 broches + PCB-03. Alimentation de labo 5,0 V sur J1 du PCB-11 (cavalier P1 retiré).
- **Logiciel :** `prog/stm32_bas`. Étapes 3 et 4 : `ESSAI_BALAYAGE_DEL 1`. Étape 5 : `ESSAI_BALAYAGE_DEL 0`, `ESSAI_CAN_LOOPBACK 1`.

## Étape 2 — PCB-11 seul (aucune carte de DEL)

| Mesure | Attendu | Obtenu | Verdict |
|---|---|---|---|
| DEL verte du PCB-11 | Allumée | Allumée | Réussi |
| J2-4 par rapport à J2-1 (5 V vers les DEL) | 5,0 V ± 5 % | 5,1 V | Réussi |
| Courant sur J1 à vide | Quelques mA | 2,7 mA | Réussi |
| PE0 (OE du translateur) | ≈ 3,3 V de la Discovery | 2,96 V | Réussi |

## Étape 3 — PCB-08 (balayage)

Câblage J2 du PCB-11 → J1 de la PCB-08 : 1→1 (GND), 2→4 (DATA→DI), 3→3 (CLOCK→CI), 4→2 (5 V→VCC). **Pas un câble droit : les fils 2 et 4 se croisent.**

| Vérification | Attendu | Obtenu | Verdict |
|---|---|---|---|
| Les 8 DEL s'allument une à une | Indice 0 = D1 … indice 7 = D8 | Conforme | Réussi |
| Ordre des couleurs | Rouge, vert, bleu, blanc | Conforme | Réussi |
| Courant pendant le balayage | < 0,3 A | 11 à 22 mA | Réussi |

## Étape 4 — PCB-03 par la PCB-06 (balayage)

Câblage J2 du PCB-11 → J6 de la PCB-06 : 1→3 (GND), 2→5 (LED_DIN), 3→4 (LED_CIN), 4→6 (P5V0). J6-1 et J6-2 non branchés. Câble Micro-Fit J2 (PCB-06) → J1 (PCB-03). Continuité vérifiée hors tension jusqu'aux points de test TP26 (5 V), TP28 (CIN), TP29 (DIN) et TP17 (GND).

| Vérification | Attendu | Verdict |
|---|---|---|
| Les 15 DEL s'allument une à une | Indice 0 = D9 … indice 14 = D23 | Réussi |
| Couleurs | Rouge, vert, bleu, blanc | Réussi |
| DEL du dessus (témoins) | Indices impairs : D10, D12, D14, D16, D18, D20, D22 | Réussi |
| Position des témoins (vue de dessus, entrée à gauche) | Sens horaire à partir de la place au-dessus de l'entrée : D10 haut-gauche, D12 haut, D14 haut-droite, D16 droite, D18 bas-droite, D20 bas, D22 bas-gauche | Réussi |
| DEL du dessous (éclairage) | Indices pairs : D9, D11, …, D23 | Réussi |

Conclusion : les tables `indice_place` et `indices_eclairage` de `T07_CONFIG_BAS` sont confirmées par le matériel.

## Étape 5 — Programme T07 sur la PCB-03 (CAN en loopback)

| # | Commande | Attendu sur la carte | Verdict |
|---|---|---|---|
| 1 | *(après RESET)* | Dessous blanc modéré (64,64,64) ; dessus éteint | Réussi |
| 2 | `del 1 0 255 0` | D10 verte ; APPLIQUE | Réussi |
| 3 | `del 4 255 0 0` | D16 rouge ; APPLIQUE | Réussi |
| 4 | `del 7 255 165 0` | D22 orange ; APPLIQUE | Réussi |
| 5 | `del 2 0 0 255 1` | D12 bleue clignotante 1 Hz ; APPLIQUE | Réussi |
| 6 | `ecl 0 255 255 255` | Dessous au blanc maximal ; APPLIQUE | Réussi (courant non noté) |
| 7 | `ecl 0 0 0 80` | Dessous bleu pâle ; APPLIQUE | Réussi |
| 8 | `hb on`, 2 s, `hb off`, 2 s | 7 témoins en jaune clignotant ; dessous reste bleu pâle | Réussi |
| 9 | `hb on`, puis `del 1 0 255 0` | D10 vert fixe ; les 6 autres restent en jaune clignotant | Réussi |
| 10 | RESET | Retour à l'état de la ligne 1 | Réussi |

## Reste à vérifier

- Courant au blanc maximal (ligne 6), et avec les 15 DEL au blanc maximal, pour le bilan d'alimentation (estimation : 0,8 à 0,9 A par PCB-03).
- Numérotation des places : T07 suppose place 1 = D10 (au-dessus de l'entrée), puis sens horaire jusqu'à place 7 = D22. À confirmer avec l'équipe (quelle ouverture est la case E1.1).
- Essai sur le vrai bus CAN avec le RPi, et délai de réponse ≤ 500 ms.
- PCB-08 avec le programme T07 en configuration BORNE (`ESA_NOEUD_BORNE`, `ecl 2 …`).
