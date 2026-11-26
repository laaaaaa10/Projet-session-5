# T12 — Essais avec le code C de T06 Bas

Base : `62f04143ca5e3598009f9902bfe51e600616764b` (PR #6 fusionnée).
Branche : `t12-integration-t06`. Essais exécutés le 26 novembre 2026.

## Ce qui est exécuté

`exemples/banc_retrait_t06.py` compile le **fichier livré**
`prog/stm32_bas/Core/Src/t06_ir.c` en bibliothèque native Linux. Le balayage,
le filtrage, les tables et la construction des trames 0x300/0x301 ainsi que le
traitement de 0x302 sont ceux du code C. Le banc appelle son API par `ctypes`.
Les callbacks de ses deux PCB-04 simulent les niveaux électriques des
récepteurs en mode faisceau coupé (`T06_PRESENCE_SI_PORTEUSE=0`).

Le bus du banc livre ces octets aux vrais T12/T11, au raccordement applicatif
T12 et au modèle de stationnement. Les paiements utilisent le vrai T02 avec
des comptes temporaires ; T13 est le vrai gestionnaire de service.

Le transport CAN, les heartbeats des deux nœuds, la rampe/Haut, les moteurs,
la sécurité, T04, le badge et l'horloge restent **simulés**. Cet essai n'exécute
ni `main.c`, ni `noeud.c`, ni les pilotes HAL/I2C, ni le firmware ARM complet.
Il ne mesure pas les délais sur matériel. Aucun accès à `can0`, aucun flash
et aucune modification des comptes réels.

## État vérifiable

| Élément | Développé | Testé en simulation | Testé sur matériel | Raccordé à l'application principale |
| --- | --- | --- | --- | --- |
| T12 ↔ T06 Bas livré | Banc d'intégration ajouté | Oui : vrai C et vrai Python | Non pour cette liaison avec le Pi | Non ; assemblage réel T12 toujours indisponible |
| T06 Bas seul | Livré par William | 44/44 vérifications dans chacun des deux modes | Rapports de William : PCB-04 et deux nœuds CAN Bas/Borne ; pas encore le Pi | Appelé par le firmware Bas ; essais Pi encore requis |
| T06 Haut / rampe | Détecteur 0x310/0x311 non livré dans le code examiné | Double explicite | Non selon le rapport du 26 novembre | Non |
| T04 / sécurité / mouvements réels | Contrats T12 conservés | Partenaires simulés | Non dans ces essais | Non ; fabrique T12 désactivée |

Le circuit 7 de chacune des PCB-04 du Bas est le passage du bras. T06 le lit
mais ne le publie pas comme détecteur de rampe. Il ne remplace donc pas le
0x311 manquant. Le protocole nomme 0x311 « IR_ENTREE_COMPLET » : sa capacité à
confirmer la présence puis le départ sur la **rampe de sortie** reste à valider.

## Résultats

**9 nouveaux tests d'intégration réussis**, aucun ignoré :

- Cycle complet après 30 s d'attente : lecture 0x302 avant gel, puis après
  paiement ; compteurs inchangés acceptés pour des états complets inchangés.
- Prise de la place 10 : son absence provient du filtrage C et de
  `0x300 [09 00 01]`. La place reste logiquement occupée jusqu'au départ manuel
  de la rampe simulée et à l'unique clôture de T04 simulé.
- Détecteur Haut absent avant paiement : 0x301 seul ne suffit pas ; aucun gel,
  débit ni ordre mécanique. Sa réponse tardive ne relance rien.
- Détecteur Haut absent après paiement : arrêt verrouillé, débit conservé,
  aucune mécanique ni clôture automatique.
- Bas non validé au démarrage, ou une seule PCB-04 présente : état invalide
  refusé avant paiement.
- Erreur de carte pendant la mécanique : validité C à zéro, arrêt T12/T13,
  retour de validité sans reprise automatique.
- Correspondance des 14 indices C aux places T12, avec les deux cartes
  parcourues circuit par circuit ; impulsion de 30 ms filtrée.
- Passage du bras sans fausse présence ni faux départ de rampe.

**247 tests Python de régression réussis**, aucun ignoré, dont ces 9 tests.
**44/44 vérifications C T06** dans chacun des deux modes de détection.
Les deux démonstrations ci-dessous réussissent. Les sources STM32 livrées par
les autres membres ne sont pas modifiées.

## Reproduire sur PC Linux

Depuis la racine de ce dépôt. Prérequis : un compilateur `cc` ou `gcc`.
S'il manque sur Debian : `sudo apt install build-essential`.

```bash
~/.venvs/esa-t13/bin/python -B prog/rpi/outils/demo_retrait_t06.py --scenario nominal
~/.venvs/esa-t13/bin/python -B prog/rpi/outils/demo_retrait_t06.py --scenario haut-absent
QT_QPA_PLATFORM=offscreen ~/.venvs/esa-t13/bin/python -B -m unittest discover -s prog/tests -p 'test_t12*.py' -q
```

Le script compile dans un dossier temporaire, affiche le SHA-256 du fichier
C puis les trames qu'il produit. `nominal` finit TERMINE/HORS_SERVICE avec
une clôture simulée. `haut-absent` finit INTERROMPU/ARRET_VERROUILLE avec zéro
clôture, zéro gel et zéro débit. Les heartbeats restent simulés dans ce cas :
on vérifie précisément l'absence de réponse du détecteur Haut.

Commande de régression utilisée (PyQt6 6.10.0 et python-can 4.6.1 installés) :

```bash
PYTHONPATH=prog/tests:prog/rpi:prog QT_QPA_PLATFORM=offscreen \
  ~/.venvs/esa-t13/bin/python -B -m unittest \
  test_t12_t06_compile test_t12_lecture_ir test_t12_raccordement \
  test_t12_retrait test_t12_paiement test_interface_graphique \
  test_interface_t04 test_comptes_transactions test_t11_depot \
  test_t13_service test_t13_service_mqtt test_t05_billets -q
```

Sans compilateur C, les 9 nouveaux tests sont ignorés : cela ne valide pas
l'intégration. Sans PyQt6/python-can, leurs tests respectifs restent également
non validés. Chaque banc utilise sa propre bibliothèque C et ses données
temporaires : le module C possède un état global.

## Ce qui reste avant un retrait réel

1. Essai de lecture seule avec le vrai Pi et le Bas : 0x302 → 0x301, variations
   0x300, validité et délais. Le firmware livré active encore le faux RPi sur
   le Bas (`ESSAI_FAUX_RPI`) : le désactiver pour cet essai avec le vrai Pi.
2. Livrer/valider T06 Haut et le détecteur de la rampe. Confirmer la numérotation
   officielle des places avec l'équipe avant de fixer la table de production.
3. Fournir les vraies observations de sécurité, l'adaptateur T13 et les
   confirmations de T08/T09/T10, puis les essayer sur matériel.
4. Raccorder le vrai T04 pour le montant, les 60 secondes, le paiement unique
   et la clôture durable. `integration_t04.py` retourne toujours `None`.

Sources : [T06 C](../stm32_bas/Core/Src/t06_ir.c),
[API T06](../stm32_bas/Core/Inc/t06_ir.h),
[aiguillage du nœud](../stm32_bas/Core/Src/noeud.c),
[rapport matériel Bas/Borne](../tests/t06/essai_t06_t07_deux_noeuds_2026-11-26.md),
[rapport PCB-04](../tests/t06/essai_ir_banc_2026-11-25.md),
[tests d'intégration](../tests/test_t12_t06_compile.py),
[activation T12](application/integration_t12.py),
[activation T04](application/integration_t04.py).
