# T12 — Préparation du retrait et contrat proposé avec T04

Portée de ce document : premier incrément financier. La machine mécanique et
son état sont décrits dans [ESSAIS_T12.md](ESSAIS_T12.md). Le raccordement
Qt/T01 développé ensuite est documenté dans [RACCORDEMENT_T12.md](RACCORDEMENT_T12.md) ;
les constats ci-dessous décrivent le premier incrément historique.

Base examinée : `ea44e864102d025fb74f18d0a5f13d0d8857482f` (26 novembre 2026).
Ce premier incrément porte sur la demande et le paiement. Il ne réalise aucun
mouvement, aucune clôture, aucune libération de place, et ne remplace pas T04.

## État vérifiable

| Élément | Développé | Testé en simulation | Testé sur matériel | Raccordé à l'application principale |
| --- | --- | --- | --- | --- |
| Contrat T12/T04 et préparation financière | Oui | Oui, tests `test_t12_paiement.py` | Non | Non |
| T02 utilisé pour les débits du banc | API existante réutilisée | Vrai service et CSV temporaires | Aucun essai ajouté | Aucun changement au raccordement existant |
| T04 pour ces essais | Double explicite | Oui | Non | Non |
| Séquence mécanique T12, IR et clôture | Non dans cet incrément | Non | Non | Non |
| Adaptation T13 et exclusion T11/T12 | Non dans cet incrément | Non | Non | Non |

## Responsabilités

- **T04** calcule et fige le montant, conserve l'heure de dépôt, ouvre et expire
  la fenêtre de 60 secondes, attribue les IDs de tentative, consomme seul les
  résultats T02 et persiste le statut financier. Après un refus, il ouvre une
  nouvelle tentative sans changer le montant ni prolonger l'échéance.
- **T02** débite intégralement une carte par son API existante. T12 ne lit et
  n'écrit aucun CSV de comptes et ne consomme pas `lire_resultats_paiement()`.
- **T12** identifie la demande, enregistre son ID avant confirmation, suit les
  instantanés T04 et refuse toute conclusion de paiement sans reçu cohérent.
  Ce composant ne donne encore aucune autorisation mécanique.

`api/retrait.py` définit les instantanés immuables et les quatre méthodes
proposées pour T04 :

| Méthode | Effet |
| --- | --- |
| `identifier_transaction(numero)` | Lecture seule du numéro et de la place ; `None` si inconnu |
| `figer_montant(numero, id_retrait)` | Ouvre la fenêtre et demande le paiement ; même ID = même gel |
| `consulter_retrait(id_retrait)` | Renvoie un instantané corrélé, sans consommer de notifications |
| `annuler_retrait(id_retrait)` | Annule l'attente puis réconcilie le résultat durable ; ne rembourse pas |

Un instantané contient la transaction, la place, le montant en centimes, les
bornes de la fenêtre, le statut et, pour `PAYE`, le reçu intégral d'une seule
carte et l'instant de validation. La fenêtre est **[ouverture, ouverture + 60 s[** :
à 60,000 secondes un nouveau paiement n'est plus admis. Un paiement validé avant
l'échéance peut être communiqué à T12 après celle-ci.

Les temps monotones décrivent le processus courant. T04 devra conserver les
horodatages durables nécessaires au calcul et à la réconciliation après son
redémarrage ; ne jamais réutiliser une valeur monotone d'une ancienne exécution.

## Composant T12 livré

`modules/demande_retrait.py` fournit `GestionDemandeRetrait(facturation, journal)`.
Il prépare la partie financière du futur `GestionRetrait` de l'interface §9.2 :
il ne prétend pas implémenter sa machine mécanique complète.

```python
t12 = GestionDemandeRetrait(t04, chemin_journal_t12)
t12.autoriser_nouvelles(True)  # À terme : décision du gestionnaire de service.
t12.demander_retrait(123456, id_demande="retrait-identifiant-unique")
t12.confirmer_retrait_et_figer_montant("retrait-identifiant-unique")
t12.mettre_a_jour()           # Appel périodique dans le thread de travail.
```

La lecture du billet ne fige pas le montant. La confirmation est une action
distincte. L'appelant crée **un ID par nouvelle demande volontaire**, puis le
réutilise pour ses répétitions. Les confirmations et annulations sont également
corrélées : un ancien clic ne peut agir sur une demande plus récente.

Le retour `True` de `demander_retrait` indique une demande connue, jamais un
paiement ni un mouvement réussi. `PAYE_ATTENTE_MECANIQUE` indique uniquement la
preuve financière. L'échéance et le montant du même retrait ne peuvent changer.

Le journal SQLite T12 conserve les intentions et les références de reçus.
Après redémarrage, une demande non terminée est `INTERROMPU`, les nouvelles
demandes sont interdites, aucun paiement n'est relancé. Il n'existe pas encore
de procédure de réarmement dans ce composant ; elle devra passer par T13 et
l'intervention prévue. Le journal ne remplace pas la persistance de T04.

Une incertitude de réponse peut être réconciliée par lecture du même ID. T12 ne
crée pas un autre paiement pour contourner une erreur. Si T04 n'a aucune trace
d'une confirmation dont la réponse a été perdue, le composant reste incertain :
une résolution explicite sera nécessaire, sans mouvement automatique.

## Banc et limites

`exemples/facturation_retrait_simulee.py` est un **double T04 en mémoire**, avec
transactions et horloge simulées. Il utilise le vrai T02 via `InterfacePaiement`.
Il n'est importé ni par `main.py`, ni par le pont Qt, ni par l'écran T01.

Le banc appelle `avant_presentation()` avant chaque événement RFID, puis
`apres_presentation()` à la fin de l'appel T02. L'horloge est contrôlée. Un débit
dont la validation complète dépasse l'échéance reste incertain et n'autorise
pas le retrait ; aucun remboursement n'est inventé. Cela ne garantit pas les
délais du stockage réel : ce cas doit être traité avec le responsable T04.

**Raccordement désormais développé et testé en simulation :** le garde
`InterfaceGardePaiementRetrait` est appelé par `LecteurGardeRetrait` dans le
travailleur Qt. Le vrai T04 doit encore l'implémenter. Le problème initial était : `Borne.actualiser()` traite les
lectures RFID avant `t04.actualiser()`. Ajouter seulement un timer de 60 s dans
T12 laisserait donc passer un badge tardif. Le garde d'échéance doit être dans
le chemin de paiement propriétaire, avant chaque débit, y compris pour plusieurs
badges présents dans un même lot. Ne pas lancer ce double à côté du vrai T04
sur une même file de résultats.

Les essais de redémarrage portent sur le journal T12, avec le même double T04
encore en mémoire. Ils ne valident ni la persistance d'un vrai T04, ni la reprise
complète d'une borne. L'absence de commandes CAN est intentionnelle à cette étape.

## Essais reproductibles — PC Linux

Depuis la racine du dépôt, sans périphérique ni broker :

```bash
~/.venvs/esa-t13/bin/python -B prog/rpi/outils/demo_retrait_paiement.py
~/.venvs/esa-t13/bin/python -B -m unittest discover -s prog/tests -p 'test_t12_paiement.py' -v
```

La démonstration utilise des comptes synthétiques dans des dossiers temporaires.
Elle vérifie une carte insuffisante, une autre carte payant la totalité, les
répétitions, l'expiration exacte, le recalcul sans minute gratuite et l'arrêt.
Les tests couvrent également réponse perdue, annulation concurrente au paiement,
reçus incohérents, paiement terminé après l'échéance et redémarrage de T12.

Vérification exécutée le 26 novembre 2026 avec Python 3 : 115 tests sélectionnés,
112 réussis et 3 ignorés (2 tests CAN virtuel faute de `python-can`, 1 test Qt
faute de PyQt6). Les 30 tests T12 sont tous réussis. Commande de régression :

```bash
PYTHONPATH=prog/tests:prog/rpi:prog QT_QPA_PLATFORM=offscreen \
  ~/.venvs/esa-t13/bin/python -B -m unittest \
  test_t12_paiement test_interface_t04 test_comptes_transactions \
  test_t11_depot test_t13_service test_t13_service_mqtt -q
```

## Raccordements suivants

La version de T01 présente désormais `interface/src/hardware/services.py` et
`evenements.py`. Leur réutilisation permettra de partager le CAN et l'affichage.
Le contrat synchrone financier doit rester dans le thread de travail T02/T04 ;
les signaux Qt transporteront les demandes et les instantanés. Il faudra aussi
ajouter la confirmation explicite du montant au parcours existant.

Avant d'autoriser des mouvements : exclusion T11/T12, états de service T13,
références fiables, barrière fermée, IR de place et de rampe, séquences CAN
acceptées puis terminées et traitement des défauts. La clôture T04 et la
libération logique suivront le départ IR confirmé ; elles ne sont pas présentes
dans ce contrat financier initial.

| Position fonctionnelle | Niveau CAN | Orientation |
| --- | --- | --- |
| Prise à l'entrée et position initiale | 0 | 0 |
| Restitution sur la rampe supérieure | 1 | 0 |
| Places E1.x / E2.x | 1 / 2 | 1 à 7 |

Au commit examiné, le firmware STM32 Haut utilise encore des étages internes
1 à 3. La traduction vers les niveaux CAN 0 à 2 reste à raccorder et à vérifier
sur les capteurs. `ParkingHigh_Home/Store/Retrieve/IsBusy` sont des squelettes :
leur retour ne prouve aucun mouvement. `ParkingHigh_Process()` contient aussi
une boucle de démonstration du plateau sous `PARKING_DEMO_LOOP`, activée dans
l'en-tête courant. Ces éléments doivent être traités par le responsable STM32
avant un essai mécanique orchestré ; T12 ne les modifie pas.

## Sources

- [Interface individuelle T12 v1.3, §9–11](https://chatgpt.com/library?file_id=libfile_fde3_f-f2346d41f4ec8191915f538eaff982d4_cbe6ad3528f08191af91018d1e714e05&account_id=personal).
- [Document maître v0.5, responsabilités T04 et T12](https://chatgpt.com/library?file_id=libfile_fde3_f-96f3293aafc8819180ba1661fb8a615c_cbe6ad3528f08191af91018d1e714e05&account_id=personal).
- [Énoncé v1.3, retrait et paiement](https://chatgpt.com/library?file_id=libfile_fde3_f-dd526ff11b7081918b31629458cf4676_cbe6ad3528f08191af91018d1e714e05&account_id=personal).
- [Protocole CAN v1.6](https://chatgpt.com/library?file_id=libfile_fde3_f-67e570a787608191abef1b7ce91e43ab_cbe6ad3528f08191af91018d1e714e05&account_id=personal).
- [Contrat T04/T02 existant](INTERFACE_T04_T02.md), [service T13](api/service_t13.py), [T11](modules/depot.py).
- [État du STM32 Haut](../stm32_haut/README.md), [commandes et démonstration](../stm32_haut/Core/Src/parking_high.c).
