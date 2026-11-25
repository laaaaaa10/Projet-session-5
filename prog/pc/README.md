# T13 — Supervision PC

**Interface opérateur, 25 novembre :** la [console PC](INTERFACE_PC.md) remplace
la fenêtre unique de diagnostic. Elle propose cinq pages et démarre en plein
écran sans barre de titre ; F11 et Quitter restent accessibles dans l'application.
Le client, le journal durable et le contrat MQTT sont conservés.

Les sections ci-dessous documentent les jalons précédents ; les limites et
essais actuels de l'interface sont regroupés dans [INTERFACE_PC.md](INTERFACE_PC.md).

**Ajout du 25 novembre :** le [banc de service simulé](ESSAIS_SERVICE_T13.md)
permet maintenant de tester les quatre commandes de service avec T11/T12
simulées, journal durable et indication explicite dans l'écran PC. L'activation
se fait uniquement avec `serveur_t13.py --simuler-service`. Le bilan du premier
jalon ci-dessous décrit le mode normal, où les modules réels restent non raccordés.

État vérifié le 25 novembre 2026, base Git `0ccfd7fa7ddf9118e73319b1c8f8201087c88635`.
Branche de travail : `integration-t13`. **T13 n'est pas terminé.**

Ce jalon permet à l'application PC de consulter et créditer les comptes T02
par MQTT, de reprendre une demande sans double crédit et de signaler des
données périmées. La fenêtre PC est distincte du banc graphique T02 et de
l'application principale Pi de T01. Aucun solde actif n'a été réinitialisé.

## Audit de reprise

`main` distant était à `c401021` lors de la reprise. La branche T13 a ensuite
été synchronisée avec `0ccfd7f`, sans conflit. Les ajouts T03 (commande de
barrière et essai de calibration) et la sélection de l'UART de l'imprimante
STM32 sont conservés. La barrière n'est pas encore raccordée à T13 ; son état
fourni par T03 est estimé, sans capteur de position.
Une copie séparée et une branche dédiée ont été créées ; les autres copies
locales comportant des modifications ont été préservées. La PR nº 1, le pont
Qt et les ajouts T05/T07 de l'équipe sont conservés.

Les treize fichiers demandés dans le message de reprise ont été lus. Les
contrats T02 et les accès T03/T04/T13 sont présents. `mqtt_client.py` et
`can_bus.py` étaient des squelettes ; aucun programme PC de supervision n'était
présent. Le document maître, l'énoncé général et CAN v1.6 ont été retrouvés et
lus. L'interface individuelle T13 a ensuite été fournie le 25 novembre :
le préfixe `esa/Equipe_N/`, les huit topics et `id_commande` sont maintenant
appliqués. Le fichier est nommé v1.5 mais porte v1.4 dans son en-tête.
Les autres champs JSON restent une proposition à valider avec l'équipe.

Avant modifications, sur `c401021` : **122 tests réussis, dont 14 Qt, aucun ignoré**.
Après synchronisation avec `0ccfd7f` : **150 tests réussis, aucun ignoré**, dont 22 nouveaux
tests avec transport simulé et six essais avec un vrai broker local. Ces
six essais comprennent l'isolation des cinq équipes, la fenêtre PC Qt et
le raccordement au thread T02.

| Disponible | Limite actuelle |
| --- | --- |
| Consultation et crédit via le vrai `AccesComptes` | Comptes préconfigurés ; aucune création ni facturation PC |
| Journal PC durable avant premier envoi | Ne pas effacer ce journal pour résoudre une réponse perdue |
| Réponses corrélées, acceptation distincte du résultat | Les quatre commandes système sont refusées comme indisponibles |
| Reconnexion et instantanés complets des données disponibles | Coupure Wi-Fi réelle du montage non essayée |
| Affichage des 14 places | États `INCONNU` tant que T03/T06 ne sont pas raccordés |
| Affichage anomalies et demandes de crédit | Transactions et statistiques T04 indisponibles, jamais remplacées par des données fictives |
| Fermeture MQTT depuis `main.py` et le travailleur Qt | Lecteur/tactile réels du Pi non essayés ici |

## Organisation

| Emplacement | Responsabilité |
| --- | --- |
| `prog/commun/t13/protocole.py` | Validation et enveloppes partagées PC/Pi |
| `prog/commun/t13/configuration.py` | Paramètres explicites, sans broker par défaut |
| `prog/commun/t13/transport.py` | Paho, callbacks, file bornée, reconnexion |
| `prog/rpi/communications/mqtt_client.py` | Accès Pi au transport partagé |
| `prog/rpi/modules/supervision.py` | Traitement dans `actualiser()`, accès public T02, instantanés |
| `prog/rpi/application/integration_t13.py` | Fabrique sans QWidget, activation explicite |
| `prog/pc/demandes.py` | Journal SQLite des demandes PC immuables |
| `prog/pc/client.py` | Corrélation, retransmission, resynchronisation et péremption |
| `prog/pc/interface.py` | Pont et travailleur Qt ; réexport de la fenêtre |
| `prog/pc/fenetre.py`, `prog/pc/visuels.py` | Pages opérateur et présentation |
| `prog/pc/main.py` | Assemblage et lancement du PC |
| `prog/rpi/outils/serveur_t13.py` | Banc Pi sans matériel, avec vrai T02 et dossier explicite |

Le transport réseau ne consulte pas les comptes dans ses callbacks. Les
traitements T02 restent dans le thread de travail existant. Le PC ne charge
ni le stockage T02, ni les GPIO, ni CAN. Les montants restent des centimes.

## Réseau confirmé et raccordements restants

Le broker retenu est celui du cours, au port **1883**, avec `ESA_MQTT_TLS=0`.
Son adresse, fournie séparément, se renseigne dans `ESA_MQTT_HOTE`.
Les sorties `mosquitto_sub` fournies par l'utilisateur le 25 novembre sur le
PC Linux et le Raspberry Pi montrent chacune `CONNACK (0)` et un abonnement
QoS 1 accepté sur `esa/Equipe_1/etat`, sans identifiants fournis en ligne de
commande. Les connexions des deux appareils au broker réel sont donc validées.
Les échanges de l'application PC avec T02 sur le Pi et la coupure Wi-Fi réelle
restent à essayer ; le test d'abonnement ne les valide pas.

Restent à raccorder ou à valider :

- Validation d'équipe des champs JSON proposés et de l'extension technique
  `SYNCHRONISER`. Les topics et `id_commande` sont déjà imposés par le document.
- Raccordement aux modules fournissant places, transactions, statistiques,
  arrêt et vérification de réarmement. Le nouveau module de barrière T03
  reste sous la responsabilité de son auteur.

Le [contrat MQTT proposé](../commun/t13/CONTRAT_MQTT_PROPOSE.md) est isolé dans
le code commun pour pouvoir être adapté. Il distingue les topics imposés des
champs et mécanismes proposés.

## Installation et tests — PC Linux

Depuis la racine de cette branche :

```bash
sudo apt-get install mosquitto
python3 -m venv .venv
.venv/bin/python -m pip install -r prog/requirements-tests-t13.txt
ESA_TEST_BROKER=1 QT_QPA_PLATFORM=offscreen .venv/bin/python -B -m unittest discover -s prog/tests -p 'test_*.py' -v
```

Environnement vérifié : Python 3.12.14, Paho 2.2.0, PyQt6 6.12.1, Mosquitto 2.0.21.
Qt est réellement exécuté hors écran. `skipped` n'est pas une validation Qt.
Sans `ESA_TEST_BROKER=1`, les six tests de broker sont explicitement ignorés.
Mosquitto n'est nécessaire que pour héberger le broker, pas pour déployer le
client Pi. Si l'exécutable n'est pas dans `PATH`, définir `ESA_TEST_MOSQUITTO`.

Le banc initial aMQTT 0.11.4 a été remplacé : le nouvel essai d'isolation a
observé la livraison de messages retained de l'équipe 1 à des abonnés d'autres
équipes. Le test reste strict et utilise désormais Mosquitto.

Les tests utilisent des dossiers temporaires. Le broker démarre dans un
processus séparé sur `127.0.0.1` et un port libre. Il est arrêté à la fin.
Cela teste TCP/MQTT réel sur la machine de développement, **pas deux appareils
physiques reliés en Wi-Fi**.

## Premier essai manuel — trois terminaux sur le PC Linux

Le choix `127.0.0.1:18883` ci-dessous est exclusivement un banc local proposé.
Les deux rôles logiciels PC et Pi tournent sur le PC. Ne pas mettre cette
adresse sur le Pi pour joindre un broker hébergé ailleurs.

**PC, terminal 1 — broker local** :

```bash
.venv/bin/python -B prog/tests/banc_broker_t13.py --broker 18883
```

**PC, terminal 2 — rôle Pi avec les vrais comptes T02 dans un dossier d'essai** :

```bash
export ESA_MQTT_HOTE=127.0.0.1
export ESA_MQTT_PORT=18883
export ESA_MQTT_PREFIXE=esa/Equipe_1
export ESA_MQTT_TLS=0
.venv/bin/python -B prog/rpi/outils/serveur_t13.py --donnees "$HOME/.local/share/esa/t13-banc-pi"
```

**PC, terminal 3 — application PC** :

```bash
export ESA_MQTT_HOTE=127.0.0.1
export ESA_MQTT_PORT=18883
export ESA_MQTT_PREFIXE=esa/Equipe_1
export ESA_MQTT_TLS=0
.venv/bin/python -B prog/pc/main.py --journal "$HOME/.local/share/esa/t13-banc-pc.sqlite3"
```

Conserver ces dossiers entre les relances. Dans un dossier d'essai neuf :
Jason `11008827F9` commence à 2000 centimes ; créditer 500 le porte à 2500.
Sélectionner cette demande et cliquer sur « Renvoyer » conserve le solde,
avec `déjà traitée`. Une nouvelle recharge volontaire reçoit un autre ID.
Consulter `1100880F2D` renvoie `COMPTE_INCONNU`.

Fermer puis rouvrir le PC avec le **même journal** vérifie la reprise des ID.
Arrêter puis relancer le broker laisse les anciennes données affichées comme
périmées jusqu'à la resynchronisation. Une opération locale T02 peut continuer
pendant cette interruption.

## Raccordement à la borne — Pi, après configuration du broker réel

Les variables réseau doivent contenir les valeurs réellement retenues par
l'équipe, pas celles du banc local ci-dessus. Installer `prog/requirements-t13.txt`
dans l'environnement Python déjà utilisé par la borne. Après configuration :

```bash
# PI — conserver le lancement habituel et les permissions RFID existantes.
export ESA_T13_ACTIVER=1
python3 -B prog/rpi/main.py
```

La fabrique est aussi appelée par le pont Qt T02 dans son travailleur. Aucun
nouveau lecteur n'est créé par T13. Si le lancement habituel utilise `sudo`,
ses variables d'environnement doivent être transmises explicitement selon la
configuration du Pi ; ne pas supposer que `sudo` les conserve.

Ne pas lancer deux serveurs Pi sur le même préfixe. Le banc `serveur_t13.py`
sert à essayer le raccordement avant d'activer la borne réelle.

## Prochain jalon : supervision et commandes de service

Les responsabilités CAN et mécaniques ne sont pas développées à la place des
autres modules. Prévoir un adaptateur explicite aux modules disponibles et un
double de simulation clairement signalé pour les autres.

Le protocole CAN v1.6, section 13, et l'interface T13, sections 12.2–12.4, imposent :

- Les états `EN_SERVICE`, `MISE_HORS_SERVICE`, `HORS_SERVICE` et
  `ARRET_VERROUILLE`. La réinitialisation est une procédure.

- `METTRE_HORS_SERVICE` refuse immédiatement de nouvelles transactions,
  annule les non confirmées et laisse finir une transaction confirmée avant
  de passer à `HORS_SERVICE`.
  Sans confirmation, libérer la réservation ; si un véhicule reste devant
  la barrière, demander son retrait et empêcher un nouveau chargement.
  Un dépôt est confirmé après billet reçu ou numéro noté et chargement
  autorisé ; un retrait l'est après paiement intégral et retrait autorisé.
- `ARRET_IMMEDIAT` émet `ARRET_RPI` **0x004**, puis garde un état verrouillé.
- `REINITIALISER` exige les défauts levés, une confirmation d'intervention
  manuelle, le bras en rétraction sûre et les références verticale et angulaire
  valides. La procédure utilise
  `REARMEMENT_CMD` **0x050** et les réponses **0x051–0x053**. Un refus ou une
  réponse manquante interdit de déclarer la réinitialisation terminée.
- La réussite ramène à `HORS_SERVICE` ; aucune reprise automatique de
  mouvement et aucune remise en service implicite.

Ces identifiants viennent du document, mais **aucune trame CAN n'est émise par
ce premier jalon**. Les codes de détail, interfaces Python et conditions de
réarmement doivent être raccordés au travail de l'équipe. L'arrêt logiciel
MQTT/CAN ne constitue pas un arrêt d'urgence matériel certifié.

| Essai à ajouter | Résultat attendu | Niveau |
| --- | --- | --- |
| Mise hors service pendant transaction confirmée | Acceptée, nouvelles transactions bloquées, fin distincte après la transaction | Double puis intégration |
| Arrêt pendant une séquence | Arrêt demandé aux modules, verrou maintenu, ancienne séquence abandonnée | Double puis CAN réel |
| Répétition/reconnexion/redémarrage pendant arrêt | Aucun déverrouillage implicite ni reprise | Double puis Pi |
| Réinitialisation refusée ou réponse manquante | Verrou conservé, aucune fausse fin | Double puis CAN réel |
| Réinitialisation confirmée après vérifications | `HORS_SERVICE`, zéro mouvement lancé | Double puis maquette |
| Remise en service avec références invalides | Refus | Double puis maquette |
| Transactions et états modifiés hors ligne | Resynchronisation fidèle au modèle Pi/T04/T06 | Intégration puis Wi-Fi réel |

## Git et revue — PC Linux

Ce jalon remplace la proposition initiale du patch `t13_jalon1_c401021.patch`,
antérieure à la réception de l'interface T13. Après publication sur GitHub,
récupérer la branche ainsi. Un worktree préserve les modifications locales :

```bash
cd ~/Projects/Projet-session-5
git status --short --branch
git fetch origin
git worktree add --track -b integration-t13 ../Projet-session-5-t13 origin/integration-t13
cd ../Projet-session-5-t13
```

Si `integration-t13` existe déjà, inspecter cette branche avant de créer le
worktree ; ne pas l'écraser. Après installation et tests, les modifications
suivantes se font dans cette branche, puis sont poussées pour revue :

```bash
# PC — vérifier que la branche affichée est integration-t13.
git branch --show-current
# Examiner puis committer uniquement les modifications voulues avant synchronisation.
git status --short
git fetch origin
git merge --no-edit origin/main
ESA_TEST_BROKER=1 QT_QPA_PLATFORM=offscreen .venv/bin/python -B -m unittest discover -s prog/tests -p 'test_*.py' -v
git push -u origin integration-t13
gh pr view --web
```

La synchronisation ci-dessus se fait dans `integration-t13`, jamais en
fusionnant T13 directement dans `main`. La PR reste en brouillon tant que le
périmètre et le contrat proposé n'ont pas été revus.

## Sources

- [Interface individuelle T13 fournie](https://chatgpt.com/library?file_id=libfile_fde3_f-09ca40cfe678819181e979db60e74858_cbe6ad3528f08191af91018d1e714e05&account_id=personal), section 12 ; nom v1.5, en-tête v1.4.
- [Accès T02 et règles des crédits](../rpi/INTERFACE_T13_T02.md).
- [Document maître ESA v0.5](https://chatgpt.com/library?file_id=libfile_fde3_f-96f3293aafc8819180ba1661fb8a615c_cbe6ad3528f08191af91018d1e714e05&account_id=personal), T13 p. 7–8 et frontières de responsabilité.
- [Énoncé ESA v1.3](https://chatgpt.com/library?file_id=libfile_fde3_f-dd526ff11b7081918b31629458cf4676_cbe6ad3528f08191af91018d1e714e05&account_id=personal), section 10.
- [Protocole CAN ESA v1.6](https://chatgpt.com/library?file_id=libfile_fde3_f-67e570a787608191abef1b7ce91e43ab_cbe6ad3528f08191af91018d1e714e05&account_id=personal), sections 4 et 13.
- [Paho Python](https://eclipse.dev/paho/clients/python/docs/), boucle réseau asynchrone et API v2.
- [Mosquitto](https://mosquitto.org/man/mosquitto-8.html), broker local d'essai.
