# T12 — Lecture des états IR avant paiement et départ

Base : `df1e1376281bd3d3f0440f6b6b614aae0b336399`, PR #5 fusionnée.
Branche : `t12-synchronisation-ir`. Vérifications du 26 novembre 2026.

Mise à jour après fusion de la PR #6 : T06 Bas est maintenant livré. Voir
[les essais T12 avec son code C](ESSAIS_T12_T06.md) et les limites du Haut.
Les résultats chiffrés ci-dessous décrivent le jalon initial de lecture IR.

## Problème traité

T12 exige des observations IR dont la réception date d'au plus 1,5 seconde
avant l'autorisation mécanique. T06 transmet les états complets sur demande,
au démarrage et toutes les 60 secondes. Une attente normale de paiement de
30 secondes rendait donc les observations initiales trop anciennes.

Le raccordement demande désormais `IR_LECTURE_CMD`, **0x302 / DLC 1 / [0xFF]**,
aux deux contrôleurs. Il attend les états complets valides **0x301** (Bas) et
**0x311** (Haut), sans commande d'actionneur :

1. À la confirmation du retrait, avant le gel du montant et le début des 60 s.
2. Après paiement validé, avant l'autorisation de la séquence mécanique.

Le gel et les reçus restent entièrement la responsabilité de T04. Les étapes
mécaniques, les niveaux CAN et l'arbitrage T11/T12 ne changent pas.

## État vérifiable

| Élément | Développé | Testé en simulation | Testé sur matériel | Raccordé à l'application principale |
| --- | --- | --- | --- | --- |
| Lecture IR non bloquante, échéance et validation | Oui | Oui, doubles et vrai ServiceCAN sur bus virtuel | Non | Appelée par le raccordement T12 existant |
| Affichage de la vérification avant/après paiement | Oui | Vraie fenêtre T01 et vrai travailleur Qt | Non | Oui, parcours Qt ; activation réelle encore bloquée |
| Cycle après 30 s de paiement | Oui | Vrais T12/T11/T13 et T02 ; T04/CAN/IR simulés | Non | Assemblage réel non activé |
| Réponse réelle des STM32 à 0x302 et cartographie des IR | Hors de cet incrément | Double explicite | Non | À livrer/valider avec T06 |

Le constructeur réel `application/integration_t12.py` continue de refuser le
retrait : T04, les observations de sécurité et l'adaptateur T13 réel manquent.
Aucun module T04 ou firmware STM32 n'a été remplacé par cette modification.

## Règles de traitement

- `modules/lecture_ir.py` gère une lecture en cours, sans attente bloquante ni
  nouvelle boucle de réception. Le CAN partagé et la file T12 sont réutilisés.
- Délai du banc : **1 seconde**, réglable par `delai_lecture_ir` au constructeur
  de `GestionRetrait`. Ce choix reste à mesurer sur matériel ; ce n'est pas une
  exigence chiffrée du protocole pour la réponse à une lecture complète.
- Une répétition de confirmation ne réémet pas et ne repousse pas l'échéance.
  Les deux réponses sont requises ; un événement de changement ne remplace pas
  un état complet. Les doublons ne prolongent pas l'attente.
- Le compteur T06 peut rester identique lorsque les états sont inchangés. Un
  compteur ancien, un compteur répété avec état contradictoire, une validité
  nulle, une longueur incorrecte ou des bits réservés non nuls ne valident pas
  une lecture. Les champs sont contrôlés avant de compter une réponse.
- Un numéro local de réception exclut les trames déjà en file avant la demande,
  même si leurs horodatages sont identiques. L'heure d'entrée du callback est
  prise avant son verrou pour exclure aussi un callback déjà commencé.
- Les réponses doivent être reçues avant l'échéance. Si elles arrivent à temps
  mais sont traitées plus tard, les contrôles de fraîcheur restent applicables.
- Réponse manquante/invalide ou sécurité perdue pendant l'attente : arrêt,
  demande interrompue, aucune reprise après une réponse tardive. Si le débit a
  déjà réussi, il reste conservé ; aucune clôture ou compensation n'est inventée.
- Annuler la vérification **avant paiement** ne déclenche pas le gel plus tard.
  Une mise hors service différée annule cette demande non confirmée ; un retrait
  déjà payé peut encore terminer. Après réinitialisation, retour à HORS_SERVICE,
  sans rejouer la lecture ni la demande interrompue.
- Une synchronisation complète ne fabrique ni prise du véhicule, ni arrivée,
  ni retrait manuel. Les transitions IR de la mécanique conservent leurs règles.

## Limites matérielles explicites

Le protocole ne fournit ni ID de requête ni horodatage d'acquisition pour ces
états IR. Les contrôles prouvent l'ordre et la fraîcheur **de réception locale**,
pas l'âge de la mesure physique. Une vieille réponse encore extérieure à la
file du RPi et reçue après la demande ne peut pas être distinguée à coup sûr
d'une réponse actuelle. T06 doit publier l'état courant validé sur demande.

Le protocole nomme 0x311 « IR_ENTREE_COMPLET ». Le banc T12 l'utilise comme
observation de rampe selon le raccordement envisagé : sa capacité à constater
le véhicule sur la rampe de sortie doit toujours être vérifiée physiquement.
La correspondance des 14 indices avec les places n'est pas inventée ici.

Au commit de base `df1e137`, le traitement Bas de 0x302 restait à ajouter.
La livraison `5f03434`, incluse dans `main` à `62f0414`, ajoute maintenant
`T06_TraiterTrame` dans `Core/Src/noeud.c` pour le Bas. Le détecteur Haut
reste à livrer. Les [essais avec le C livré](ESSAIS_T12_T06.md) complètent
ce jalon ; la liaison avec le vrai Pi et les mouvements réels restent à tester.

## Essais reproductibles — PC

Depuis la racine du dépôt contenant cette branche :

```bash
~/.venvs/esa-t13/bin/python -B prog/rpi/outils/demo_retrait_ir.py --scenario nominal
~/.venvs/esa-t13/bin/python -B prog/rpi/outils/demo_retrait_ir.py --scenario muet
QT_QPA_PLATFORM=offscreen ~/.venvs/esa-t13/bin/python -B -m unittest discover -s prog/tests -p 'test_t12*.py' -q
```

- `nominal` : 30 s de paiement, nouvelle lecture, départ autorisé après états
  frais, puis retrait manuel simulé et clôture unique ; T13 finit HORS_SERVICE.
- `muet` : paiement effectué, seconde lecture sans réponse ; arrêt verrouillé,
  aucune commande d'actionneur, aucune clôture et aucune reprise tardive.
- Suite T12 : **129 tests réussis, aucun ignoré** avec PyQt6 et python-can.
  Les nouveaux essais ajoutent 24 cas de lecture IR et un cas d'écran T01.
  Sans PyQt6/python-can, les essais correspondants sont ignorés et ne sont pas
  validés. Les versions utilisées ici sont PyQt6 6.10.0 et python-can 4.6.1.

Régression exécutée : **238 tests réussis, aucun ignoré** :

```bash
PYTHONPATH=prog/tests:prog/rpi:prog QT_QPA_PLATFORM=offscreen \
  ~/.venvs/esa-t13/bin/python -B -m unittest \
  test_t12_lecture_ir test_t12_raccordement test_t12_retrait test_t12_paiement \
  test_interface_graphique test_interface_t04 test_comptes_transactions \
  test_t11_depot test_t13_service test_t13_service_mqtt test_t05_billets -q
```

Sources : [protocole CAN ESA v1.6, §6 et §10](https://chatgpt.com/library?file_id=libfile_fde3_f-67e570a787608191abef1b7ce91e43ab_cbe6ad3528f08191af91018d1e714e05&account_id=personal),
[raccordement T12](RACCORDEMENT_T12.md), [tests IR](../tests/test_t12_lecture_ir.py),
[traitement CAN du STM32 Bas](../stm32_bas/Core/Src/noeud.c).
