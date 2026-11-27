# Tests sur PC — T07 (William MacDonald)

Ces tests compilent le **vrai code** de `prog/stm32_bas` avec un faux HAL (`fake_hal/`, `fake_main/`). Aucun matériel n'est nécessaire. Il faut un `gcc` pour PC : MSYS2/MinGW, WSL ou Linux.

| Fichier | Ce qui est vérifié | Résultat (26 nov. 2026) |
|---|---|---|
| `test_rgb_led_chain.c` | Trame APA102 (début, DEL en B-G-R, fin), refus des paramètres invalides, DMA occupé, envoi bloquant sans DMA | 31/31 |
| `test_t07_del.c` | Commandes 0x340 et 0x130, réponses selon la fonction (0x341 places 1–7, 0x342 places 8–14, 0x350/0x351/0x352 niveaux 0/1/2), refus (place 0 ou 15, niveau 3, mode 2, DLC, niveau 0 sans DEL sur le BAS), places et niveaux d'un autre nœud ignorés, clignotement 1 Hz, perte et retour du RPi, SPI occupé, configurations BAS (places 1–7), BORNE (places 8–14 + niveau 1) et HAUT (niveau 2), configurations invalides refusées, configuration d'essai BAS_BANC (BAS + éclairage du niveau 0), ambiance des parkings du HAUT (rouge au démarrage, T07_ReglerAmbiance, refusée sur le BAS), surcouche d'animation (T07_DefinirSurcouche : les commandes restent traitées, seule la DEL modifiée change, retrait = image normale) | 89/89 |
| `test_disco.c` | Animation disco par la surcouche de T07 : 40 images/s, intensité limitée, arc-en-ciel qui tourne, stroboscope (flashs courts, blanc tous les 4 temps), poursuite (une tête qui avance toutes les 60 ms) ; zones tout / parkings / dessous (HAUT : parkings seuls, dessous intact et commandes 0x130 encore appliquées ; dessous seul, ambiance intacte ; BORNE : parkings = places ; BAS sans éclairage : zone vide), retour à l'image de T07 à l'arrêt | 40/40 |
| `test_noeud.c` | Heartbeat 0x042 toutes les 500 ms, détection du RPi (0x040), perte après 1,5 s, aiguillage des commandes vers T07 | 13/13 |

Depuis ce dossier (`prog/tests/t07`) :

```
gcc -Wall -Wextra -Ifake_main -Ifake_hal -I../../stm32_bas/Drivers/BSP/RgbLedChain -I../../stm32_bas/Core/Inc test_rgb_led_chain.c ../../stm32_bas/Drivers/BSP/RgbLedChain/rgb_led_chain.c -o test_rgb_led_chain
gcc -Wall -Wextra -Ifake_main -Ifake_hal -I../../stm32_bas/Drivers/BSP/RgbLedChain -I../../stm32_bas/Core/Inc test_t07_del.c ../../stm32_bas/Core/Src/t07_del.c ../../stm32_bas/Drivers/BSP/RgbLedChain/rgb_led_chain.c -o test_t07_del
gcc -Wall -Wextra -Ifake_main -Ifake_hal -I../../stm32_bas/Drivers/BSP/RgbLedChain -I../../stm32_bas/Core/Inc test_noeud.c ../../stm32_bas/Core/Src/noeud.c ../../stm32_bas/Core/Src/t07_del.c ../../stm32_bas/Core/Src/t06_ir.c ../../stm32_bas/Drivers/BSP/RgbLedChain/rgb_led_chain.c -o test_noeud
gcc -Wall -Wextra -Ifake_main -Ifake_hal -I../../stm32_bas/Drivers/BSP/RgbLedChain -I../../stm32_bas/Core/Inc test_disco.c ../../stm32_bas/Core/Src/disco.c ../../stm32_bas/Core/Src/t07_del.c ../../stm32_bas/Drivers/BSP/RgbLedChain/rgb_led_chain.c -o test_disco
./test_rgb_led_chain && ./test_t07_del && ./test_noeud && ./test_disco
```

Chaque programme affiche « N/N vérifications réussies » et retourne 0 si tout passe.
