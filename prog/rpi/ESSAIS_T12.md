# T12 — Orchestration du retrait : deuxième incrément

Base : `ea44e864102d025fb74f18d0a5f13d0d8857482f`, examinée le 26 novembre 2026.
La préparation financière du premier incrément reste dans
[INTERFACE_T12_T04.md](INTERFACE_T12_T04.md). Ce document décrit la mécanique,
l'arbitrage et leur banc d'essai. Le raccordement Qt/T01 ajouté ensuite est décrit
séparément dans [RACCORDEMENT_T12.md](RACCORDEMENT_T12.md) : parcours branché,
partenaires réels encore bloquants. Les résultats ci-dessous sont ceux du
jalon mécanique, avant ce raccordement.

## État vérifiable

| Élément | Développé | Testé en simulation | Testé sur matériel | Raccordé à l'application principale |
| --- | --- | --- | --- | --- |
| Demande, fenêtre de paiement et journal T12 | Oui | 30 tests financiers | Non | Non |
| Machine mécanique et journal T12 | Oui | Oui | Non | Non |
| Exclusion T11/T12 sur le CAN partagé | Oui | Vraies machines T11 et T12 | Non | T11 utilise l'arbitre ; T12 reste à brancher |
| États de service T13 appliqués à T12 | Adaptateur de banc | Vrai gestionnaire T13 | Non | Non |
| Coupure MQTT pendant une séquence T12 | Scénario de test | Transports MQTT simulés, vrais client et superviseur | Non | Non |
| Moteurs, IR, barrière, références, calibrations | Contrats utilisés | Doubles explicites | Non | Non |
| Facturation et clôture T04 | Contrat proposé | Double en mémoire, vrai T02 sur comptes temporaires | Non | Non |

Vérification exécutée : **168 tests sélectionnés, 165 réussis, 3 ignorés**.
Les 53 nouveaux tests mécaniques/service et les 30 tests financiers T12 passent.
Les tests ignorés sont deux essais T11 sur CAN virtuel (`python-can` absent)
et un essai graphique T13 (PyQt6 absent). Le banc T12 n'ouvre ni SocketCAN,
ni `python-can`, ni connexion à un broker réel.

## Exécution sur le PC

Depuis la racine de la branche `integration-t12`, avec le Python habituel :

```bash
~/.venvs/esa-t13/bin/python -B prog/rpi/outils/demo_retrait.py --scenario nominal
~/.venvs/esa-t13/bin/python -B prog/rpi/outils/demo_retrait.py --scenario ir-muet
~/.venvs/esa-t13/bin/python -B prog/rpi/outils/demo_retrait.py --scenario arret
~/.venvs/esa-t13/bin/python -B -m unittest discover -s prog/tests -p 'test_t12*.py' -v
```

Le scénario nominal imprime chaque commande CAN simulée. Il demande une mise
hors service pendant le retrait, attend la présence en sortie, puis injecte un
retrait manuel simulé. La clôture est unique, la place devient libre et T13 finit
en `HORS_SERVICE`. Le scénario `ir-muet` garde la place logique occupée et verrouille
l'arrêt. Le scénario `arret` vérifie la réinitialisation vers `HORS_SERVICE`, sans
reprendre la transaction interrompue. Les trois scénarios utilisent des dossiers
temporaires et ne touchent pas aux comptes actifs.

Régression ciblée, sur PC :

```bash
PYTHONPATH=prog/tests:prog/rpi:prog QT_QPA_PLATFORM=offscreen \
  ~/.venvs/esa-t13/bin/python -B -m unittest \
  test_t12_retrait test_t12_paiement test_interface_t04 test_comptes_transactions \
  test_t11_depot test_t13_service test_t13_service_mqtt -q
```

Aucune commande de mouvement réel à exécuter sur le Raspberry Pi à cette étape.

## Séquence et preuves exigées

1. Paiement complet validé par la préparation T12/T04 ; zone de sortie libre,
   barrière fermée, trajet déclaré valide, références disponibles et heartbeats
   Haut/Bas récents. Acquisition de l'arbitre commun.
2. Lecture des trois actionneurs : bras rétracté estimé, niveau 0 avec référence
   verticale détectée, orientation 0 référencée. Une simple acceptation ne suffit
   pas à valider une lecture dans cette implémentation.
3. Accès à la place : élévation niveau 1/2 puis rotation 1–7.
4. Prise : bras déployé, soulèvement, rétraction. Attente de l'absence IR de la
   place avant tout transport vers la sortie. La place reste occupée logiquement.
5. Transport sortie : rotation 0 puis élévation 1 **dans le banc**. L'autre ordre
   est configurable ; le choix réel exige validation mécanique et des câbles.
6. Restitution au niveau **1 / orientation 0** : déploiement, abaissement,
   rétraction. Retour de l'ascenseur au niveau **0 / orientation 0** ; aucune
   nouvelle entrée tant que le cycle n'est pas libéré.
7. Présence sortie, puis absence par un événement IR ultérieur. Un état complet
   de synchronisation ne fabrique pas un départ. La fin du retour mécanique est
   également requise avant l'appel de clôture à T04.

Les positions de bras et de rotation restent **estimées**, conformément au CAN.
Pour un déplacement entre niveaux, T12 exige `ELEVATION_ETAT.DB4 = 2`, qui signifie
référence du niveau détectée puis position finale estimée après correction.
Cela ne constitue pas une mesure indépendante de la position finale.

## Responsabilités et interfaces

- [GestionRetrait](modules/retrait.py) compose le composant financier existant.
  `autoriser_apres_paiement(id_demande)` est explicite ; les répétitions d'un même
  ID ne redémarrent pas la séquence. La fabrique s'abonne au `ServiceCAN` reçu,
  sans ouvrir un autre bus.
- Le callback CAN met les trames dans une file bornée. `mettre_a_jour()` traite
  la file, les délais, SQLite et T04 dans le **même thread de travail** que le
  composant financier. Le pont Qt respecte maintenant cette propriété (voir le
  document de raccordement).
- [ArbitreMecanique](modules/arbitrage_mecanique.py) est associé à l'objet CAN.
  T11 et T12 acquièrent le même propriétaire exclusif. Le verrou reste occupé
  pendant l'attente IR et le retrait manuel ; un défaut empêche une autre tâche
  de reprendre la mécanique. Une émission est sérialisée avec le verrouillage.
- T11 conserve sa séquence et son API. Les modifications portent sur
  l'acquisition/libération du verrou et les numéros de séquence communs.
  Ses validations moteur et sa table IR provisoire ne sont pas validées par T12.
- [ConditionsRetrait](api/mecanique_retrait.py) doit provenir du propriétaire réel
  de la sécurité/barrière : observations horodatées, défauts levés, références et
  trajet validés. Aucun champ sûr n'est vrai par défaut. Le producteur réel manque.
- La correspondance des 14 places avec les indices IR est **obligatoire** au
  constructeur. `TABLE_IR_SIMULEE` est une convention du banc uniquement.
- T04 reste seul consommateur de la file de résultats de paiement. La clôture
  proposée est `cloturer_sortie(id_retrait, transaction_id, place)` avec reçu
  corrélé `SortieCloturee`. **T04** réalise la clôture durable et la libération
  logique de ses ressources. T12 ne libère pas directement la place.
- Une réponse de clôture perdue laisse `CLOTURE_INCERTAINE` et conserve l'exclusion.
  `reconcilier_cloture()` est une lecture explicite de `consulter_sortie()`, avec
  conditions mécaniques sûres. Aucun rejeu de mouvement ou de débit.

## Défauts, service et redémarrage

Une acceptation doit arriver en 500 ms maximum ; la fin est une réponse distincte.
Les doublons d'acceptation ne prolongent pas le délai. Une fin sans acceptation,
un mauvais état final, un défaut spontané, une trame mal formée, une référence
inconnue, la saturation de la file ou une erreur de journal arrêtent la progression.
T12 demande l'arrêt logiciel prioritaire existant `ARRET_RPI` (`0x004`). L'émission
ne prouve pas l'immobilisation réelle du matériel.

Le délai de fin vaut 30 s et celui des confirmations IR 5 s dans le banc ; ils
restent à régler sur la mécanique. Les heartbeats Haut/Bas sont surveillés à
1,5 s. Une communication qui revient après cette limite ne fait pas reprendre
la séquence. L'attente du retrait manuel n'a pas de timeout de clôture automatique.

`METTRE_HORS_SERVICE` interdit les nouvelles demandes, laisse finir une demande
confirmée et attend le départ. Une demande non confirmée est annulée. Si le
paiement expire, aucune mécanique ne commence. `ARRET_IMMEDIAT` interrompt et
verrouille. Après intervention simulée et réinitialisation, T13 revient à
`HORS_SERVICE`. Une transaction interrompue reste à résoudre avant une remise
en service ; elle n'est ni effacée ni rejouée automatiquement.

Le journal mécanique est écrit avant l'émission de chaque commande. Après
redémarrage, toute opération non terminée reste interrompue et bloque l'arbitre.
Les essais de redémarrage ne prouvent pas la persistance du double T04, qui reste
en mémoire. Le vrai T04 devra rendre paiement et clôture durables et idempotents.
Un seul processus de borne doit posséder ce CAN ; l'arbitre est local au processus.

**Limite explicite du banc T12 :** les séquences 1 à 254 ne sont pas réutilisées
pendant la vie du processus partagé. À épuisement, le système refuse de progresser ;
un acquittement ne recycle pas les numéros. Le protocole n'a pas de numéro d'époque
pour distinguer une très vieille réponse après bouclage. La stratégie de recyclage
et de purge doit être convenue avant exploitation continue. T11 seul, sans T12
instancié sur son CAN, conserve son bouclage historique excluant `0xFF`.

## Reste à raccorder et valider

Le vrai T04 est toujours absent d'`application/integration_t04.py`. Les confirmations
de sécurité, la barrière et la cartographie IR réelle restent à fournir. Le contrôle
d'échéance doit aussi être raccordé avant chaque débit dans le thread propriétaire
T02/T04, comme expliqué dans le document financier.

L'interface T01 et le transport MQTT existants sont préservés. Le prochain raccordement
réutilisera leurs objets partagés et signaux ; le double de banc ne doit pas remplacer
silencieusement un module réel dans `Services` ou `./esa`.

Le STM32 Haut examiné contient encore des commandes `Home/Store/Retrieve/IsBusy`
incomplètes, une démonstration automatique activée et une numérotation interne
1–3 à traduire vers les niveaux CAN 0–2. Les contrats d'arrêt, de résultat final,
de référencement et le capteur de sortie doivent être validés sur matériel avant
un essai réel T12.

## Sources

- [Interface T12 v1.3, §9–11](https://chatgpt.com/library?file_id=libfile_fde3_f-f2346d41f4ec8191915f538eaff982d4_cbe6ad3528f08191af91018d1e714e05&account_id=personal).
- [Protocole CAN v1.6, §4–6](https://chatgpt.com/library?file_id=libfile_fde3_f-67e570a787608191abef1b7ce91e43ab_cbe6ad3528f08191af91018d1e714e05&account_id=personal).
- [Énoncé v1.3](https://chatgpt.com/library?file_id=libfile_fde3_f-dd526ff11b7081918b31629458cf4676_cbe6ad3528f08191af91018d1e714e05&account_id=personal).
- [T11](modules/depot.py), [contrat de service T13](api/service_t13.py), [gestionnaire T13](modules/service_t13.py), [service CAN commun](communications/can_bus.py).
- [Tests mécaniques et service](../tests/test_t12_retrait.py), [banc explicite](exemples/banc_retrait.py), [état STM32 Haut](../stm32_haut/README.md).
