# Tests sur PC — T07 (William MacDonald)

Ces tests compilent le **vrai code** de `prog/stm32_bas` avec un faux HAL (`fake_hal/`, `fake_main/`). Aucun matériel n'est nécessaire. Il faut un `gcc` pour PC : MSYS2/MinGW, WSL ou Linux.

| Fichier | Ce qui est vérifié | Résultat (24 nov. 2026) |
|---|---|---|
| `test_rgb_led_chain.c` | Trame APA102 (début, DEL en B-G-R, fin), refus des paramètres invalides, DMA occupé, envoi bloquant sans DMA | 31/31 |
| `test_t07_del.c` | Commandes 0x340 et 0x130, réponses 0x341/0x342/0x350–0x352, refus (place 0 ou 15, niveau 3, mode 2, DLC), places d'un autre nœud ignorées, clignotement 1 Hz, perte et retour du RPi, SPI occupé, configurations BAS, HAUT et BORNE | 56/56 |
| `test_noeud.c` | Heartbeat 0x042 toutes les 500 ms, détection du RPi (0x040), perte après 1,5 s, aiguillage des commandes vers T07 | 13/13 |

Depuis ce dossier (`prog/tests/t07`) :

```
gcc -Wall -Wextra -Ifake_main -Ifake_hal -I../../stm32_bas/Drivers/BSP/RgbLedChain -I../../stm32_bas/Core/Inc test_rgb_led_chain.c ../../stm32_bas/Drivers/BSP/RgbLedChain/rgb_led_chain.c -o test_rgb_led_chain
gcc -Wall -Wextra -Ifake_main -Ifake_hal -I../../stm32_bas/Drivers/BSP/RgbLedChain -I../../stm32_bas/Core/Inc test_t07_del.c ../../stm32_bas/Core/Src/t07_del.c ../../stm32_bas/Drivers/BSP/RgbLedChain/rgb_led_chain.c -o test_t07_del
gcc -Wall -Wextra -Ifake_main -Ifake_hal -I../../stm32_bas/Drivers/BSP/RgbLedChain -I../../stm32_bas/Core/Inc test_noeud.c ../../stm32_bas/Core/Src/noeud.c ../../stm32_bas/Core/Src/t07_del.c ../../stm32_bas/Drivers/BSP/RgbLedChain/rgb_led_chain.c -o test_noeud
./test_rgb_led_chain && ./test_t07_del && ./test_noeud
```

Chaque programme affiche « N/N vérifications réussies » et retourne 0 si tout passe.
