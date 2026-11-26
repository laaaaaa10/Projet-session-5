# T13 — Essais de service avec T11/T12 simulées

Version du 25 novembre 2026. Base : `90d982c` avec la correction de sélection
`a3b7257`. Le patch de service ne remplace pas l'interface finale : la fenêtre
reste un banc de diagnostic. Aucun pilote moteur, GPIO ou CAN n'est ouvert.

## Installation

Appliquer le patch depuis la racine du dépôt, sur le PC et sur le Pi qui
exécutent T13. Le chemin ci-dessous suppose le fichier téléchargé dans
`~/Downloads`; adapter uniquement ce chemin si nécessaire.

```bash
git status --short --branch
git apply --check "$HOME/Downloads/t13_service_simule.patch" && git apply "$HOME/Downloads/t13_service_simule.patch"
```

Le contrôle précède toute modification. Si le contrôle échoue, conserver le
message et vérifier la version du dépôt ; ne pas appliquer en force. Les
ajouts de l'équipe et les comptes existants ne sont pas remplacés.

## Lancement sur le montage PC ↔ broker MQTT ↔ Pi

Conserver les variables `ESA_MQTT_HOTE`, `ESA_MQTT_PORT`, `ESA_MQTT_PREFIXE`
et `ESA_MQTT_TLS` déjà utilisées avec succès. Les deux appareils doivent
viser le même broker et le même préfixe d'équipe. Arrêter l'ancien serveur
T13 avant de lancer celui-ci : un seul serveur Pi par préfixe.

Les commandes `python3` supposent l'environnement Python habituel de T13,
avec Paho côté Pi et Paho/PyQt6 côté PC. Si un venv est utilisé, l'activer
avant de lancer les commandes. Se placer à la racine du dépôt sur chaque appareil.

**Pi, terminal serveur :**

```bash
python3 -B prog/rpi/outils/serveur_t13.py \
  --donnees "$HOME/.local/share/esa/t13-service-sim" \
  --simuler-service
```

Ce dossier séparé conserve les données de ce banc. Les comptes préconfigurés
y sont créés s'il est neuf ; les soldes de la borne réelle ne sont pas utilisés.
Le verrou d'arrêt y persiste entre les redémarrages. Conserver le dossier
pendant les essais de reprise, sans effacer son journal.

**PC, terminal interface :**

```bash
python3 -B prog/pc/main.py \
  --journal "$HOME/.local/share/esa/t13-service-sim-pc.sqlite3"
```

Une bannière « SIMULATION T03/T11/T12 et sécurité CAN » doit apparaître,
avec l'état `HORS_SERVICE` et les quatre boutons de service disponibles.
Les places et transactions réelles restent indisponibles.

**Pi, deuxième terminal :** définir cette fonction pour injecter les événements
du banc. Elle utilise exactement le même dossier que le serveur.

```bash
scenario() {
  python3 -B prog/rpi/outils/scenario_service_t13.py \
    --donnees "$HOME/.local/share/esa/t13-service-sim" "$1"
}
```

Attendre de voir l'événement dans « Service simulé » sur le PC avant la
commande suivante (publication périodique au maximum toutes les cinq secondes).
Il s'agit d'une injection **locale au banc**, pas d'une commande MQTT ajoutée.

## Essais manuels

Les commandes de service se font avec les boutons du PC. Les commandes
`scenario` se font sur le Pi dans le deuxième terminal.

| Essai | Actions | Résultat attendu |
| --- | --- | --- |
| Service sans transaction | Cliquer REMETTRE EN SERVICE puis METTRE HORS SERVICE | `EN_SERVICE`, puis `HORS_SERVICE`; deux réponses finales identifiées |
| Réservation non confirmée | Remettre en service, `scenario reservation`, mettre hors service | Réservation annulée, `HORS_SERVICE`, rampe encore occupée; remise en service refusée jusqu'à `scenario retirer-vehicule` |
| Dépôt confirmé | Remettre en service, `scenario depot`, mettre hors service | `MISE_HORS_SERVICE`, réponse `ACCEPTEE`, aucune nouvelle transaction autorisée |
| Fin du dépôt | `scenario fin-sequence` | `HORS_SERVICE` et réponse `TERMINEE` avec l'ID initial de mise hors service |
| Retrait confirmé | Remettre en service, `scenario retrait`, mettre hors service, `scenario fin-sequence` | Reste `MISE_HORS_SERVICE` et `ATTENTE_RETRAIT_MANUEL` |
| Sortie manuelle | `scenario retirer-vehicule` | Passe à `HORS_SERVICE`, demande de mise hors service terminée |
| Arrêt pendant mouvement | Remettre en service, `scenario depot`, cliquer ARRET IMMEDIAT | `ARRET_VERROUILLE`, séquence `INTERROMPUE`, aucune reprise |
| Verrou persistant | Cliquer REMETTRE EN SERVICE; déconnecter/reconnecter, puis relancer le serveur avec le même dossier | Remise en service refusée, verrou conservé après reconnexion et redémarrage |
| Réinitialisation prématurée | Cliquer REINITIALISER avant intervention | `REFUSEE / REARMEMENT_NON_SUR` |
| Intervention et réarmement | `scenario intervention`, puis **nouveau clic** REINITIALISER | Acceptation, puis `HORS_SERVICE`; aucune reprise de séquence |
| Réponse absente | Arrêter, `scenario intervention`, `scenario rearmement-muet`, nouveau clic REINITIALISER | Après cinq secondes, `REARMEMENT_SANS_REPONSE`, verrou conservé |
| Réarmement refusé | `scenario intervention`, `scenario rearmement-refuse`, nouveau clic REINITIALISER | `REARMEMENT_REFUSE`, verrou conservé |
| Retour au mode normal du double | `scenario rearmement-ok`, `scenario intervention`, nouveau clic REINITIALISER | `HORS_SERVICE`; remise en service distincte nécessaire |
| Défaut local | En service, `scenario defaut` | Verrou et anomalie publiés; nouvelles transactions interdites |
| Référence invalide | Hors service, `scenario reference-invalide`, cliquer REMETTRE EN SERVICE | `SYSTEME_NON_PRET` |

Après un refus, un **nouveau clic** crée une nouvelle demande. Le bouton
« Renvoyer avec le même ID » retrouve volontairement la décision précédente,
même si les conditions ont changé. Répéter une ancienne remise en service ne
déverrouille donc pas un arrêt plus récent. L'état courant est affiché en haut;
la réponse d'une ancienne commande reste un résultat historique.

Pour vérifier la progression hors ligne : commencer une mise hors service
pendant un retrait confirmé, couper MQTT, puis injecter localement
`fin-sequence` et `retirer-vehicule`. Au retour de MQTT, le PC doit retrouver
`HORS_SERVICE` et la réponse finale, sans recommencer le retrait.

## Contrat pour le raccordement réel

`api/service_t13.py` propose un adaptateur non bloquant. Le gestionnaire de
service conserve les règles et le journal ; l'adaptateur fournit les états
réels de T03/T11/T12 et les confirmations de sécurité. L'actuel adaptateur
`SystemeT13Simule` sera remplacé au moment de l'intégration de ces tâches.

Un adaptateur réel devra interdire les nouveaux dépôts/retraits et chargements,
libérer une réservation non confirmée, maintenir une transaction confirmée
jusqu'à sa fin complète, propager l'arrêt aux séquences et émettre `ARRET_RPI`
sur le ServiceCAN partagé. Le réarmement devra utiliser `REARMEMENT_CMD` et
attendre toutes les confirmations prévues au protocole, avec des références
réellement fiables. Une simple transmission CAN ne constitue pas ce résultat.

L'intervention manuelle et les références proviennent des modules locaux;
elles ne sont jamais acceptées comme paramètres des boutons MQTT du PC.
L'événement local `intervention` ne fait que les **simuler** sur ce banc.
La réponse `ARRET_VERROUILLE` atteste le verrou et la demande d'arrêt au double,
pas une mesure physique de l'arrêt des moteurs. Le test matériel reste à faire.

## Validation effectuée

- 23 nouveaux tests de service, dont deux avec un vrai broker Mosquitto local.
- 205 tests du dépôt réussis, aucun ignoré, avec Qt hors écran et MQTT réel local.
- Essai supplémentaire : serveur lancé dans un processus distinct avec
  `--simuler-service`, injection par l'outil de scénario et utilisation des
  quatre boutons dans la fenêtre Qt reliée au broker. Cycle complet réussi.
- Scénarios couverts : confirmation distincte de l'acceptation, sortie manuelle,
  arrêt et défaut, prérequis du réarmement, refus/absence de réponse, changement
  de conditions pendant réarmement, doublons, redémarrage, perte du broker et
  resynchronisation. Les tests utilisent des dossiers temporaires.

Commande de vérification, avec Mosquitto installé et les dépendances de test :

```bash
ESA_TEST_BROKER=1 QT_QPA_PLATFORM=offscreen \
python3 -B -m unittest discover -s prog/tests -p 'test_*.py' -v
```

Ces résultats valident le banc logiciel. Le raccordement aux véritables
T11/T12, les trames CAN sur le montage et l'interface utilisateur finale
restent à intégrer et à valider.

Sources : [interface T13, sections 12.2–12.8](https://chatgpt.com/library?file_id=libfile_fde3_f-09ca40cfe678819181e979db60e74858_cbe6ad3528f08191af91018d1e714e05&account_id=personal),
[document maître, T13 et validation](https://chatgpt.com/library?file_id=libfile_fde3_f-96f3293aafc8819180ba1661fb8a615c_cbe6ad3528f08191af91018d1e714e05&account_id=personal).
