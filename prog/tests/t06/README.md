# Tests sur PC — T06 (William MacDonald)

Ces tests compilent le **vrai code** de `prog/stm32_bas/Core/Src/t06_ir.c` avec deux cartes PCB-04 **simulées** (véhicule, parasite, erreurs I2C). Aucun matériel n'est nécessaire. Il faut un `gcc` pour PC : MSYS2/MinGW, WSL ou Linux.

| Fichier | Ce qui est vérifié | Résultat (25 nov. 2026) |
|---|---|---|
| `test_t06_ir.c` | Émetteurs éteints à l'init ; un seul émetteur allumé à la fois ; 1er 0x301 après validation, sans 0x300 ; changement confirmé en 250 ms ou moins (pire cas sur 40 changements : 101 ms) ; impulsion de 30 ms filtrée ; indices des deux cartes (0–13, bits de DB0/DB1) ; passage du bras lu mais pas publié ; 0x302 (cibles 1, 0xFF, 2, DLC) ; SYNCHRO_CMD 0x080 ; parasite et erreur I2C → validité 0 puis retour ; 0x301 toutes les 60 s ; banc avec une seule carte | 44/44 dans chacun des deux sens de détection |

Depuis ce dossier (`prog/tests/t06`), les deux sens de détection (réflexion, faisceau coupé) :

```
gcc -Wall -Wextra -DT06_PRESENCE_SI_PORTEUSE=1 -I../../stm32_bas/Core/Inc test_t06_ir.c ../../stm32_bas/Core/Src/t06_ir.c -o test_t06_ir_reflexion
gcc -Wall -Wextra -DT06_PRESENCE_SI_PORTEUSE=0 -I../../stm32_bas/Core/Inc test_t06_ir.c ../../stm32_bas/Core/Src/t06_ir.c -o test_t06_ir_faisceau
./test_t06_ir_reflexion && ./test_t06_ir_faisceau
```

Chaque programme affiche « N/N vérifications réussies » et retourne 0 si tout passe.
