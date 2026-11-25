# Contrat MQTT T13 — topics imposés, enveloppes JSON proposées

L'interface T13 fournie le 25 novembre impose les huit topics et le champ
`id_commande`. Les autres champs JSON, QoS, temporisations et mécanismes de
resynchronisation ci-dessous sont **une proposition à valider par l'équipe**.
Le fichier s'appelle `ESA_Interfaces_logicielles_T13_Supervision_MQTT_v1.5.docx`
mais son en-tête porte « Version 1.4 — 9 novembre 2026 » : cette implémentation
se base sur le contenu fourni, notamment la section 12.5.

## Configuration et topics

Le PC et le Pi doivent viser le même broker et le même préfixe obligatoire
`esa/Equipe_N/`, avec N de 1 à 5 et la casse exacte. Un seul serveur Pi possède
ce préfixe. Les variables `ESA_MQTT_HOTE`, `ESA_MQTT_PORT`,
`ESA_MQTT_PREFIXE` et `ESA_MQTT_TLS` (`0` ou `1`) sont obligatoires.
`ESA_MQTT_UTILISATEUR`, `ESA_MQTT_MOT_DE_PASSE` et `ESA_MQTT_CA` sont optionnelles
selon le broker. Aucun mot de passe dans Git. Les certificats TLS sont vérifiés.

| Topic imposé | Émetteur | QoS proposé | Retain proposé | Contenu |
| --- | --- | --- | --- | --- |
| `esa/Equipe_N/etat` | Pi | 1 | Oui | État général, soldes disponibles, statistiques et disponibilité des modules |
| `esa/Equipe_N/places` | Pi | 1 | Oui | État des 14 places |
| `esa/Equipe_N/anomalies` | Pi | 1 | Oui | Anomalies disponibles |
| `esa/Equipe_N/transactions` | Pi | 1 | Oui | Transactions disponibles |
| `esa/Equipe_N/commande/reponse` | Pi | 1 | Non | Réponse aux commandes générales |
| `esa/Equipe_N/comptes/reponse` | Pi | 1 | Non | Réponse aux demandes de comptes |
| `esa/Equipe_N/commande` | PC | 1 | Non | Commandes générales |
| `esa/Equipe_N/comptes/commande` | PC | 1 | Non | Consultation/crédit |

Un crédit reçu sur le topic général est refusé. Aucun abonnement avec joker
ne traverse les préfixes des équipes. Il n'existe plus de topic supplémentaire
`disponibilite` : le testament utilise `etat`, avec le message proposé
`{"version":1,"type":"disponibilite","en_ligne":false}`.

MQTT 3.1.1, sessions propres, réabonnement après reconnexion. Retenter une
demande est une décision applicative ; un PUBACK ne confirme pas un crédit.
Le PC conserve ses demandes sur disque. Le Pi conserve les crédits via T02.
Les commandes livrées avec le drapeau retained sont refusées. Tous les
émetteurs autorisés doivent publier les commandes avec `retain=False` : en
MQTT 3.1.1, un abonnement déjà actif ne permet pas toujours de constater
qu'un émetteur a demandé le stockage retained de son message.

La section 12.1 n'exige aucune authentification pour le projet. Les clients
fonctionnent donc sans identifiants ; TLS et authentification restent des
options si le broker retenu les utilise. Le broker local de test est anonyme
et écoute uniquement `127.0.0.1`. Son adresse n'est pas celle du montage réel.

## Commandes et réponses

```json
{"version":1,"id_commande":"t13:credit-0123456789abcdef0123456789abcdef","commande":"AJOUTER_CREDIT","parametres":{"id_uart":"11008827F9","montant_centimes":500}}
```

Pour un crédit, **`id_commande` sert aussi d'ID durable de transaction T02**.
Il est créé une seule fois côté PC, avec le préfixe `t13:credit-` et un UUID.
Ce choix de contrat simplifie la correspondance sans générer d'ID à la
réception. Il est distinct des références temporaires du pont Qt local.

Le journal SQLite du PC enregistre l'enveloppe complète avant son premier
envoi. Reconnexion, réponse perdue, redémarrage ou bouton « Renvoyer »
réutilisent exactement cette enveloppe. Une nouvelle recharge volontaire
crée un nouvel ID. Ne pas supprimer le journal PC pour résoudre une demande
incertaine. Il est lié au broker et au préfixe de sa borne.

| Commande | Paramètres exacts | Disponibilité |
| --- | --- | --- |
| `CONSULTER_SOLDE` | `id_uart` | Accès T02 réel |
| `AJOUTER_CREDIT` | `id_uart`, `montant_centimes` | Accès T02 réel, anti-doublons de T02 |
| `SYNCHRONISER` | Objet vide | Commande technique **proposée** ; instantané du Pi |
| `METTRE_HORS_SERVICE` | Objet vide | Banc explicite `--simuler-service` ; indisponible sans adaptateur |
| `REMETTRE_EN_SERVICE` | Objet vide | Même banc ; validation des conditions locales |
| `ARRET_IMMEDIAT` | Objet vide | Même banc ; verrou T13 et demande d'arrêt au double |
| `REINITIALISER` | Objet vide | Même banc ; attente de confirmation du réarmement simulé |

`SYNCHRONISER` est une extension technique proposée sur `commande`, pas une
commande imposée par le professeur. Elle permet de vérifier la fraîcheur du
Pi sans confondre une ancienne publication retained avec une réponse actuelle.
L'équipe doit valider cette extension avec le reste du format JSON. Les quatre
commandes système sont actives uniquement avec un adaptateur de service.
Le banc `--simuler-service` fournit cet adaptateur en simulation explicite.
La borne normale conserve le refus `MODULE_INDISPONIBLE` jusqu'au raccordement réel.

Les identifiants UART sont les dix caractères hexadécimaux complets, en
majuscules dans ce contrat. Le crédit est un entier strictement positif ;
booléens, flottants, chaînes, paramètres supplémentaires et clés JSON répétées
sont refusés. Les autres ID suivent la syntaxe publique de T02 (128 caractères
maximum). Taille maximale d'un message : 64 Kio.

```json
{"version":1,"id_commande":"t13:credit-0123456789abcdef0123456789abcdef","commande":"AJOUTER_CREDIT","phase":"ACCEPTEE","code":"DEMANDE_VALIDEE","donnees":{}}
```

| Phase | Interprétation PC |
| --- | --- |
| `ACCEPTEE` | Demande validée et acheminée ; conserver l'attente |
| `TERMINEE` | Résultat obtenu ; consulter le code et le reçu pour connaître l'issue |
| `REFUSEE` | Demande refusée ou procédure interrompue ; le code précise l'issue, sans succès annoncé |
| `INCERTAINE` | Incident technique ; garder la demande et le même ID pour la reprise |

Un crédit terminé contient `donnees.recu`, avec les champs de
`ResultatOperation` : ID, date UTC, type, carte, montant, statut, soldes
historiques et `deja_traitee`. `COMPTE_INCONNU` est une issue enregistrée,
pas un crédit réussi. Le PC vérifie que le reçu correspond à la carte, au
montant et à l'ID demandés. Une acceptation retardée ne remplace pas un résultat
final. Le solde courant est obtenu séparément dans l'instantané.

## Resynchronisation et données périmées

Le Pi publie un instantané toutes les cinq secondes et après reconnexion,
réparti entre `etat`, `places`, `anomalies` et `transactions`. Chaque fragment
porte la même session et la même révision ; le PC attend les quatre fragments
avant de remplacer l'affichage, sans mélanger deux révisions. L'instantané
contient une session aléatoire par démarrage et une révision croissante,
les soldes disponibles et la disponibilité des modules. Dans ce premier
jalon, les 14 places sont explicitement `INCONNU` ; état de service, arrêt
verrouillé, transactions T04 et statistiques ne sont pas inventés.

Le PC conserve l'affichage mais le marque périmé dès une déconnexion, un
testament hors ligne, un changement de session ou quinze secondes sans état
frais. Un instantané retained ne suffit pas à rétablir la fraîcheur : le PC
exige d'abord la réponse à sa nouvelle demande `SYNCHRONISER`. Les révisions
répétées ou anciennes ne rafraîchissent pas les données.

Les demandes sans réponse finale sont retransmises toutes les trois secondes
après cette synchronisation. Le service dispose d'un journal durable séparé
de T02 : un même ID retrouve sa réponse, sans répéter les effets. Une ancienne
réponse `EN_SERVICE` reste historique ; l'instantané publié donne l'état courant.
Une nouvelle tentative après un refus exige un nouvel ID (nouveau clic sur le
bouton). Un redémarrage ne restaure jamais `EN_SERVICE` automatiquement.

## Extension de service simulé — 25 novembre 2026

Les quatre commandes conservent leurs paramètres vides. Le Pi vérifie les
conditions locales dans `api/service_t13.py` : le PC ne peut pas déclarer les
références valides ou confirmer une intervention par un paramètre MQTT.
Dans le banc seulement, `scenario_service_t13.py ... intervention` simule cette
confirmation et les vérifications mécaniques. Les méthodes de cet adaptateur
sont une proposition de raccordement à valider avec les auteurs de T03/T11/T12.

Champs supplémentaires proposés dans `etat` : `service_simule` (booléen),
`diagnostic_service` (objet), `incident_service` (code ou null) et
`commande_service_en_cours` (ID ou null). `disponibilite.service` signifie
que cet adaptateur est raccordé ; les disponibilités **réelles** T03/T11/T12
restent fausses. Le diagnostic simulé ne remplit ni les transactions T04,
ni les places IR. Le PC affiche une bannière explicite de simulation.

Mise hors service confirmée : `ACCEPTEE/TRANSACTION_A_TERMINER`, puis
`TERMINEE/HORS_SERVICE` avec le même ID après la fin locale. En retrait,
la fin inclut le retrait manuel du véhicule. Un arrêt interrompt la procédure
avec `REFUSEE/INTERROMPUE_PAR_ARRET` et `interrompue=true` ; l'arrêt reçoit son
propre résultat corrélé. `TERMINEE/ARRET_VERROUILLE` atteste le verrou logiciel
et la demande d'arrêt à l'adaptateur, jamais une position physique mesurée.

Réinitialisation : vérifier d'abord les cinq conditions de l'interface T13,
publier `ACCEPTEE/REARMEMENT_EN_COURS`, attendre un résultat positif du double
et vérifier de nouveau les conditions. Sans résultat dans les cinq secondes
(temporisation proposée), conserver le verrou avec `REARMEMENT_SANS_REPONSE`.
Un refus, un nouveau défaut, une condition perdue ou un redémarrage conserve
également le verrou. Le succès mène uniquement à `HORS_SERVICE`.

Les fichiers `service-simule.sqlite3` et `scenario-service.json` appartiennent
au dossier d'essai. Le premier conserve les verrous et décisions, le second
injecte un événement local unique. Le serveur ignore l'ancien événement au
démarrage. Attendre la prise en compte affichée avant d'injecter le suivant.
La progression locale continue pendant toute déconnexion MQTT.

Les callbacks réseau déposent les messages dans une file de 256 éléments.
`actualiser()` traite au maximum huit commandes côté Pi. Les débordements
sont comptés et les demandes sans réponse sont reprises avec leur ID durable.
Les écritures T02 restent synchrones dans la boucle de travail existante.
Aucune attente de réseau n'y est ajoutée ; le PC utilise son propre thread Qt
pour le réseau et SQLite.

## Sources

- [Interface individuelle T13 fournie](https://chatgpt.com/library?file_id=libfile_fde3_f-09ca40cfe678819181e979db60e74858_cbe6ad3528f08191af91018d1e714e05&account_id=personal), sections 12.1, 12.5 et 12.6 ; nom v1.5, en-tête v1.4.
- [Contrat T13/T02 du dépôt](../../rpi/INTERFACE_T13_T02.md).
- [Document maître ESA v0.5](https://chatgpt.com/library?file_id=libfile_fde3_f-96f3293aafc8819180ba1661fb8a615c_cbe6ad3528f08191af91018d1e714e05&account_id=personal), T13 p. 7–8.
- [Énoncé ESA v1.3](https://chatgpt.com/library?file_id=libfile_fde3_f-dd526ff11b7081918b31629458cf4676_cbe6ad3528f08191af91018d1e714e05&account_id=personal), section 10.
- [Eclipse Paho Python](https://eclipse.dev/paho/clients/python/docs/), API de callbacks v2, boucle réseau, sessions et limites de persistance.
- [MQTT — Eclipse Mosquitto](https://mosquitto.org/man/mqtt-7.html), QoS, messages retained et testament.

Les topics, le champ `id_commande` et les frontières viennent du document T13.
Les autres champs, l'extension de synchronisation, les limites et les
temporisations demeurent des choix de cette proposition.
