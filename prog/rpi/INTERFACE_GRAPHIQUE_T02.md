# Raccordement graphique de T02 — PyQt6

Le raccordement est fourni par `interface/qt/pont_t02.py`. Il réutilise la borne,
le service de comptes et le stockage existants. Une fenêtre de démonstration
permet d'essayer ses commandes avant le branchement des pages du projet.

Le programme console `main.py` reste utilisable sans PyQt6. Le squelette
`interface/ecran_tactile.py` reste disponible pour le responsable de l'écran.
La fenêtre livrée est un **banc T02** : les montants sont saisis pour les essais.
Le calcul des factures appartient toujours à T04, la réservation à T03 et
le transport MQTT à T13.

## Essayer sur le PC Linux

Sur Debian, installer la dépendance graphique avec le Python du système :

```bash
sudo apt update && sudo apt install python3-pyqt6
cd ~/Projects/Projet-session-5
python3 -B prog/rpi/outils/demo_interface_graphique.py
```

Autre possibilité sur PC Linux, dans un environnement virtuel :

```bash
python3 -m venv .venv-qt
.venv-qt/bin/python -m pip install -r prog/rpi/requirements-qt.txt
.venv-qt/bin/python -B prog/rpi/outils/demo_interface_graphique.py
```

Par défaut, la fenêtre utilise **des données temporaires** et trois boutons
qui simulent les présentations des badges. Elle n'ouvre aucun UART/GPIO.
La simulation fournit des événements logiques `ACCEPTE` ; elle ne vérifie pas
l'électronique du lecteur. La validation des trames reste couverte par les
tests RFID et les essais sur le Pi.

Parcours dans une fenêtre neuve :

1. Présenter Jason : compte reconnu, 20,00 $, aucun débit.
2. Préparer un paiement de 500 centimes, puis présenter Jason : `PAIE`, 15,00 $.
3. Rejouer le même ID : résultat enregistré, toujours 15,00 $.
4. Ajouter 500 centimes à Jason : `CREDITE`, 20,00 $. Rejouer le crédit : toujours 20,00 $.
5. Préparer 2500 centimes puis présenter Lucia : `SOLDE_INSUFFISANT`, toujours 20,00 $.
6. Faire une nouvelle demande puis présenter la carte inconnue : `COMPTE_INCONNU`.
7. Préparer une demande puis annuler l'attente : aucun débit ; une nouvelle demande reste possible.
8. Fermer la fenêtre : elle attend la fin de l'opération en cours et la fermeture du lecteur.

Le bouton de répétition garde **le montant et l'ID de l'ancienne opération**, même
si le champ de montant a changé depuis. Une nouvelle demande utilise un nouvel ID.
Après un refus terminal, une nouvelle tentative exige un nouvel ID.
Après une erreur de fichier, reprendre le même ID. Une réponse déjà enregistrée
affiche son résultat historique ; le tableau relit séparément les soldes courants.

Pour garder les comptes d'essai entre deux lancements :

```bash
python3 -B prog/rpi/outils/demo_interface_graphique.py \
  --donnees "$HOME/esa-t02-graphique"
```

Le mode et le caractère temporaire ou persistant des données sont affichés
en haut de la fenêtre. La référence de la dernière opération est sélectionnable
pour la copier. La gestion persistante des factures de T04 n'est pas remplacée
par cette fenêtre d'essai.

## Essayer avec le lecteur du Pi

Après commit/push sur le PC et pull sur le Pi, installer `python3-pyqt6` sur le
Pi aussi. Lancer depuis **sa session graphique**, avec les mêmes bibliothèques
matérielles que pour `main.py`. Arrêter d'abord tout autre lecteur avec Ctrl+C.

Avec les droits matériels utilisés actuellement sur le montage :

```bash
cd ~/Projects/Projet-session-5
sudo -E python3 -B prog/rpi/outils/demo_interface_graphique.py --lecteur-reel
```

Ce lancement utilise encore des comptes temporaires. Pour utiliser explicitement
les comptes actifs persistants du projet, ajouter :

```bash
sudo -E python3 -B prog/rpi/outils/demo_interface_graphique.py --lecteur-reel \
  --donnees "$HOME/Projects/Projet-session-5/prog/rpi/donnees/actives"
```

`-E` conserve l'environnement de la session graphique. L'accès à l'affichage
dépend de la session X11/Wayland ; un terminal SSH sans affichage ne suffit pas
à faire apparaître la fenêtre. Si le compte du Pi dispose déjà des permissions
UART/GPIO et des fichiers, le programme peut être lancé sans sudo.

Les options `--port`, `--gpio`, `--chip`, `--delai-ms` restent disponibles.
Les boutons de badges sont absents en mode réel. Une commande de simulation
est également refusée par le travailleur dans ce mode.

## Organisation et exécution

| Fichier | Rôle |
| --- | --- |
| `application/borne.py` | `actualiser()` traite un passage ; `executer()` conserve la boucle console |
| `interface/qt/pont_t02.py` | Commandes asynchrones, signaux Qt et cycle de vie du lecteur |
| `interface/qt/fenetre_demo.py` | Fenêtre du banc ; aucun accès direct aux CSV ou au matériel |
| `exemples/lecteur_simule.py` | Source d'événements pour la démonstration PC |
| `outils/demo_interface_graphique.py` | Assemblage de l'application de démonstration |

Un `QThread` possède le travailleur. Celui-ci construit les services, ouvre le
lecteur et utilise un `QTimer` de 2 ms pour appeler `Borne.actualiser()`.
Les commandes de l'écran sont mises en file par Qt et exécutées dans ce même
thread, y compris les consultations de solde. Les écritures CSV ne bloquent
donc pas le thread de l'écran. Les callbacks de l'interface reçoivent les
résultats dans le thread graphique.

Le traitement peut prendre plus de 2 ms selon les fichiers et le matériel :
c'est un intervalle demandé, pas une garantie de temps réel. Les modules
T03/T04/T13 doivent toujours rendre la main rapidement dans `actualiser()`.

## Utiliser le pont dans le futur écran

La fenêtre principale possède **un seul** `PontT02Qt`, partagé par ses pages.
Connecter les signaux avant `demarrer()` et attendre `pret` pour envoyer les
commandes. Les noms de callbacks ci-dessous sont à fournir par le responsable UI :

```python
from interface.qt.pont_t02 import PontT02Qt
from modeles.comptes import DemandePaiement

self.t02 = PontT02Qt(parent=self)  # vrai lecteur, comptes actifs par défaut
self.t02.pret.connect(self.afficher_comptes)
self.t02.carte_lue.connect(self.afficher_identification)
self.t02.paiement_en_attente.connect(self.afficher_attente)
self.t02.resultat_paiement.connect(self.afficher_resultat)
self.t02.reponse.connect(self.traiter_reponse)
self.t02.erreur.connect(self.afficher_erreur)
self.t02.avertissement.connect(self.afficher_avertissement)
self.t02.arrete.connect(self.terminer_fermeture)
self.t02.demarrer()

# Plus tard, avec le montant et l'ID stable fournis par T04 :
reference = self.t02.demander_paiement(DemandePaiement(id_tentative, montant_centimes))
```

Les méthodes de commande **retournent une référence de requête, pas la valeur
du service**. Attendre `reponse(reference, action, valeur)` ou
`erreur(IncidentQt)`. Ne pas donner ce pont aux fabriques qui attendent les
API synchrones `InterfaceIdentification`, `InterfacePaiement` ou `InterfaceComptes`.

| Commande du pont | Valeur reçue dans `reponse` |
| --- | --- |
| `consulter_solde(id_uart)` | Entier en centimes, ou `None` pour un compte inconnu |
| `lister_soldes()` | Copie `{id_uart: solde_centimes}` |
| `ajouter_credit(id_transaction, id_uart, montant_centimes)` | `ResultatOperation` |
| `retrouver_resultat_credit(id_transaction)` | Résultat enregistré ou `None` |
| `demander_paiement(DemandePaiement(...))` | `None` : commande prise en compte, pas une confirmation de paiement |
| `retrouver_resultat_paiement(id_transaction)` | Résultat enregistré ou `None` |
| `annuler_paiement(id_transaction)` | Booléen : attente effectivement annulée |
| `simuler_badge(id_uart)` | `None` ; disponible en simulation uniquement |

**Deux références différentes :** la référence de requête Qt identifie un
aller-retour avec l'écran ; elle change à chaque appel. L'`id_transaction`
identifie l'opération durable et reste identique lors d'une retransmission.
Le responsable T04/T13 garde cet ID dans son propre suivi persistant.

Les autres signaux sont :

| Signal | Données et usage |
| --- | --- |
| `pret` | Tuple des comptes, après l'ouverture réussie du lecteur |
| `carte_lue` | `IdentificationCarte`, seulement hors paiement |
| `paiement_en_attente` | `DemandePaiement` à présenter à l'utilisateur |
| `resultat_paiement` | Copie du résultat à afficher, y compris une répétition historique |
| `paiement_annule` | ID de l'attente annulée |
| `evenement_rfid` | Événement technique du lecteur, pour le diagnostic |
| `avertissement` | Message technique, notamment une récupération CSV |
| `erreur` | `IncidentQt(reference, action, type_erreur, message, fatal)` |
| `arrete` | Thread terminé et fermeture du lecteur tentée ; les éventuels échecs sont signalés par `erreur` |

Un incident avec `fatal=True` termine le travailleur. Une erreur de commande
(paramètre invalide, conflit, incident CSV) revient à l'appelant avec sa référence.
Un incident CSV peut survenir après l'enregistrement du résultat : conserver le
même ID. Une erreur technique ne devient jamais un faux `COMPTE_INCONNU` ou `PAIE`.

Les fabriques `integration_t03/t04/t13.py` sont utilisées dans le thread de
travail. Elles construisent **la logique des modules**, jamais leurs `QWidget`.
T01 construit les pages dans le thread graphique. Il faudra donc séparer le
contrôleur et la page si un futur module regroupe les deux dans une même classe.

Quand T04 est branché, il reste l'unique consommateur de sa file de résultats.
Le signal d'affichage en observe une copie et ne la vide pas. Sans module T04,
le pont joue le rôle de client du banc et vide cette file après notification.
La file de T03 reste réservée à T03. Les règles de navigation des pages et les
actions après un paiement relèvent des contrôleurs T03/T04, pas des signaux de
diagnostic du banc.

## Fermeture propre

`arreter()` met l'arrêt en file et retourne immédiatement. Une opération déjà
en cours finit avant la fermeture du lecteur. Attendre **`arrete`** avant de
détruire le pont, sa fenêtre ou de quitter l'application. Ne pas employer
`QThread.terminate()` ni détruire le thread pendant qu'il fonctionne.

Le `closeEvent` de la fenêtre de démonstration montre ce parcours : ignorer
provisoirement la fermeture, désactiver les commandes, appeler `arreter()`,
puis fermer réellement à réception du signal. Après un arrêt, le même pont
peut être redémarré ; les anciens résultats restent retrouvables dans le journal.

## Tests

```bash
QT_QPA_PLATFORM=offscreen python3 -B -m unittest discover -s prog/tests -p 'test_*.py' -v
```

Sans PyQt6, les tests graphiques sont indiqués `skipped` ; cela ne valide pas
le raccordement Qt. Avec PyQt6, ils créent les vrais objets Qt et les vrais CSV
temporaires. Ils exercent les boutons, les signaux, les reprises, un stockage
volontairement ralenti, les conflits et la fermeture. Le parcours lecteur
utilise le vrai module RFID avec UART/GPIO simulés.

Le code a été vérifié avec PyQt 6.12.1 / Qt 6.12.0. L'affichage et le tactile
sur le Pi restent à observer sur le montage.

Sources techniques : [Qt — Threads and QObjects](https://doc.qt.io/qtforpython-6/overviews/qtdoc-threads-qobject.html),
[Qt — QThread](https://doc.qt.io/qt-6/qthread.html),
[Riverbank — installation PyQt6](https://www.riverbankcomputing.com/software/pyqt/download),
[Debian — python3-pyqt6](https://packages.debian.org/search?keywords=python3-pyqt6).
