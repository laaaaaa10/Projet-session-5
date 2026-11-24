# T02 — Comptes RFID et paiements

T04 calcule la facture. T02 reçoit le montant en centimes, identifie la carte
et effectue le débit intégral si le compte dispose du solde nécessaire.
Un badge présenté sans demande de paiement consulte seulement le compte.

| Compte | ID UART complet | Numéro imprimé | Solde initial |
| --- | --- | --- | --- |
| Jason Duval | `11008827F9` | `0008923129` | 20,00 $ |
| Lucia Caminos | `1100823734` | `0008533812` | 20,00 $ |
| Carte inconnue | `1100880F2D` | `0008916781` | Aucun compte |

Les cartes et numéros proviennent des essais sur le Pi du 24 novembre 2026.
La recherche utilise les dix caractères de l'ID UART, jamais le numéro imprimé.
La création de comptes par interface reste hors de cette version.

## Organisation

| Fichier | Responsabilité |
| --- | --- |
| `main.py` | Assemblage, lancement et fermeture du lecteur |
| `application/borne.py` | Boucle, demande en attente, transmission des résultats à T04 |
| `api/paiements.py` | Contrat public de paiement et types importables par T04 |
| `application/integration_t04.py` | Point de branchement du futur module T04 |
| `api/identification.py` | Contrat de lecture des cartes et de consultation des soldes pour T03 |
| `application/acces_identification.py` | Accès en lecture seule fourni à T03 |
| `application/integration_t03.py` | Point de branchement du module du responsable T03 |
| `api/comptes.py` | Contrat de consultation/crédit fourni à T13 |
| `application/acces_comptes.py` | Accès T13 au service, avec le même journal et les mêmes soldes |
| `application/integration_t13.py` | Point de branchement du futur module T13 |
| `modeles/comptes.py` | Compte, demande, résultat, statuts et validation des paramètres |
| `modules/gestion_comptes.py` | Consultation, crédit, débit intégral et détection des doublons |
| `stockage/comptes_csv.py` | Lecture/écriture CSV, verrou et récupération des soldes |
| `interface/console_borne.py` | Messages console |
| `modules/lecteur_nfc_rfid.py` | UART, RNG, checksum et réarmement existants |
| `outils/simuler_t04.py` | Demande de test avec le vrai lecteur |
| `outils/comptes.py` | Consultation et crédit depuis le terminal |
| `exemples/client_t04.py` | Exemple de client utilisant seulement l'API publique |
| `outils/demo_interface_t04.py` | Démonstration sur PC Linux, dans des données temporaires |
| `outils/demo_interface_t13.py` | Démonstration de crédit répété et de consultation pour T13 |
| `outils/demo_recuperation_comptes.py` | Démonstration d'un CSV de soldes récupéré depuis le journal |

Le lecteur RFID ne connaît ni les comptes ni les tarifs. Le service de comptes
ne connaît ni GPIO, ni UART, ni l'écran. Les modules métier n'affichent rien.
L'interface Python est détaillée dans [INTERFACE_T04_T02.md](INTERFACE_T04_T02.md).
L'accès de T03 aux identifications et aux soldes est décrit dans
[INTERFACE_T03_T02.md](INTERFACE_T03_T02.md). La réservation et la commande
de barrière appartiennent au module de son responsable ; cet accès ne les réalise pas.
Le code réel de T04 n'est pas présent dans cette branche. Le point de branchement
est prêt dans `application/integration_t04.py` ; il suffit d'y retourner le futur
module, qui reçoit l'API de paiement et fournit `actualiser()`.
Aucun protocole CAN/MQTT de paiement n'est inventé ici.
L'accès consultation/crédit de T13 est décrit dans
[INTERFACE_T13_T02.md](INTERFACE_T13_T02.md). Sa fabrique retourne `None`
jusqu'au branchement du vrai module de supervision.

## Données persistantes

`donnees/comptes.csv` est le **modèle initial suivi par Git** :

```csv
id_uart,nom,solde_centimes
11008827F9,Jason Duval,2000
1100823734,Lucia Caminos,2000
```

Au premier lancement, le stockage crée le dossier **`donnees/actives/`** :

- `comptes.csv` : comptes et soldes courants ;
- `operations.csv` : résultats des crédits et paiements, y compris les refus ;
- `comptes.lock` : verrou partagé entre les programmes utilisant ces fichiers.

Ce dossier est ignoré par Git. Un `git pull` ou une modification ultérieure
du modèle ne remet donc pas les soldes à 20,00 $. Les chemins par défaut sont
calculés depuis les modules, indépendamment du répertoire de lancement.

**Modifier les soldes avec le service ou l'outil de crédit.** Le journal fait
référence : un solde courant qui ne correspond plus à sa dernière opération est
reconstruit depuis le journal. Ne pas éditer ni effacer les fichiers actifs
pour simuler un crédit. Pour sauvegarder, arrêter les programmes puis copier
ensemble `comptes.csv` et `operations.csv`.

Tous les montants sont des entiers en centimes. Un paiement peut être nul ;
un crédit doit être strictement positif. Les nombres négatifs, flottants et
booléens sont rejetés. Une carte inconnue ne crée jamais de compte.
Un solde insuffisant entraîne un refus sans débit partiel.

## Doublons et interruptions

Chaque tentative possède un ID stable, fourni par l'appelant. Répéter
exactement la même opération renvoie le résultat enregistré et ne modifie plus
le solde, même après redémarrage. Réutiliser cet ID avec un autre montant,
une autre carte ou un autre type d'opération provoque `ConflitTransaction`.

Un refus est lui aussi enregistré : après un refus reçu, une nouvelle tentative
utilise un nouvel ID. Après une erreur technique ou une réponse perdue, on
réutilise **le même ID** pour retrouver l'issue de la tentative précédente.

Les CSV sont validés sous un verrou Linux `flock`. Chaque fichier est écrit
dans un temporaire du même dossier, synchronisé, puis remplacé. Le journal est
enregistré avant le fichier des soldes. Si l'exécution s'interrompt entre les deux,
la prochaine lecture récupère le solde du journal avant une nouvelle opération.
**Les deux CSV ne constituent pas une transaction atomique globale.**
Après une récupération réussie, un avertissement technique
`STOCKAGE | RECUPERATION CSV` indique l'ID UART, l'ancien solde, le solde restauré
et le fichier concerné. Sans configuration de journalisation particulière,
cet avertissement apparaît sur la sortie d'erreur du terminal.
Un journal manquant à côté de comptes existants, ou des données incohérentes,
arrête le traitement au lieu de créer silencieusement un historique vide.

C'est un stockage local adapté à la démonstration, sous Linux et Python 3.10+.
Il relit le journal et le réécrit à chaque nouvelle opération ; ce choix simple
convient à ce petit projet, pas à un historique volumineux. Les écritures disque
peuvent allonger un passage dans la boucle. Les essais de récupération simulent
des erreurs d'E/S ; ils ne constituent pas un essai de coupure électrique du Pi.

## Vérification logicielle sur PC

Depuis la racine du dépôt :

```bash
python3 -B -m unittest discover -s prog/tests -p 'test_*.py' -v
```

Les suites RFID et comptes exercent les vrais modules, avec l'UART et le GPIO
simulés. Chaque test écrit dans un dossier temporaire : les soldes actifs du Pi
ne sont jamais utilisés par les tests.

La suite `test_interface_t04.py` vérifie aussi le contrat public et le branchement
dans le vrai `main.py`, avec un client T04 d'exemple. Une démonstration sans
matériel, utilisable sur le PC Linux ou le Pi sans sudo, est disponible :

```bash
python3 -B prog/rpi/outils/demo_interface_t04.py
```

L'accès en lecture seule pour T03 dispose aussi de son exemple et de sa démo :

```bash
python3 -B prog/rpi/outils/demo_interface_t03.py
```

La suite `test_interface_t03.py` vérifie notamment la séparation des lectures
d'identification et des cartes de paiement, avec un seul lecteur dans le vrai
programme principal et les périphériques simulés.

L'accès T13 et le signalement de récupération ont leurs démos, toujours dans
des fichiers temporaires sans MQTT ni lecteur :

```bash
python3 -B prog/rpi/outils/demo_interface_t13.py
python3 -B prog/rpi/outils/demo_recuperation_comptes.py
```

La suite `test_interface_t13.py` vérifie les crédits répétés, les conflits,
la reprise après erreur de fichier et les soldes partagés avec T03/T04.

Couverture : les trois cartes, absence de débit à la simple lecture, paiements
et crédits, solde insuffisant, doublons après redémarrage, conflits d'identifiants,
accès concurrents, erreurs avant/après confirmation du journal et parcours
complet du simulateur avec les trames RFID réelles.

## Essais sur le Pi

Le parcours complet, avec les résultats attendus et un dossier d'essai séparé,
est dans [VALIDATION_T02.md](VALIDATION_T02.md). Il couvre le crédit répété,
le refus suivi d'une autre carte, la persistance et l'observation du buzzer.

Après le push sur le PC, arrêter le programme du Pi avec **Ctrl+C**, puis :

```bash
cd ~/Projects/Projet-session-5 &&
git switch integration-rfid &&
git pull --ff-only origin integration-rfid &&
sudo python3 prog/rpi/main.py
```

Le lancement normal conserve la consultation de Jason et Lucia et le refus de
la troisième carte. Une lecture `ACCEPTE` ne signifie toujours pas `PAIE`.

Pour tester une demande de 5,00 $, **quitter d'abord main.py avec Ctrl+C** :

```bash
sudo python3 prog/rpi/outils/simuler_t04.py \
  --id-transaction essai-t04-001 --montant-centimes 500
```

Présenter Jason : pour un solde initial de 20,00 $, le résultat doit être
`PAIE` avec 15,00 $. Le simulateur quitte et libère le lecteur.
Relancer la même commande : même reçu avec `aucun nouveau mouvement`, sans
ouvrir le lecteur et sans second débit. Une autre tentative doit avoir un
autre ID, par exemple `essai-t04-002`.

Consulter puis remettre les 5,00 $ de l'essai via un crédit journalisé :

```bash
sudo python3 prog/rpi/outils/comptes.py consulter
sudo python3 prog/rpi/outils/comptes.py crediter \
  --id-transaction credit-essai-001 --id-uart 11008827F9 --montant-centimes 500
```

Répéter la commande de crédit avec le même ID ne crédite pas une deuxième fois.
Utiliser un nouvel ID pour un nouveau crédit volontaire. Ces commandes portent
sur les comptes de démonstration, sans encaissement bancaire.

Pour des essais séparés des soldes habituels, les deux outils acceptent
`--donnees /chemin/vers/un/dossier-dessai`. Garder le même dossier entre les
essais pour vérifier la persistance. Pour l'outil `comptes.py`, placer cette
option avant `consulter` ou `crediter`.

Les codes de sortie des outils sont : `0` réussite, `2` refus de compte/solde,
`1` erreur technique ou paramètres invalides dans le service
(argparse utilise aussi `2` pour une syntaxe de commande invalide).
Le simulateur retourne `130` sur Ctrl+C.

Un seul programme doit ouvrir le lecteur à la fois.
Les options RFID `--port`, `--gpio`, `--chip` et `--delai-ms` sont conservées.
Voir [README_RFID.md](README_RFID.md) pour le montage et les ressources matérielles.
