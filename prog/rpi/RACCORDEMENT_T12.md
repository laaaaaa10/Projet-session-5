# T12 — Parcours de retrait dans la borne T01

Base : `e04eb954df11c4134c042b567359a7edb7c422f0` (PR #4 fusionnée).
Branche du jalon initial : `raccordement-t12`. Vérifications du 26 novembre 2026.
La lecture IR ajoutée ensuite et ses résultats actuels sont décrits dans
[LECTURE_IR_T12.md](LECTURE_IR_T12.md). Les nombres d'essais ci-dessous sont ceux
du jalon initial de raccordement.

## Portée vérifiable

| Élément | Développé | Testé en simulation | Testé sur matériel | Raccordé à l'application principale |
| --- | --- | --- | --- | --- |
| Billet → confirmation → commandes T12 et états corrélés | Oui | Vraie fenêtre T01 et vrai travailleur Qt | Non | Oui, parcours de l'écran tactile |
| Garde T04 avant chaque badge, y compris un lot | Oui | Vrai T02, double T04 et horloge contrôlée | Non | Chemin disponible dans le travailleur ; vrai T04 absent |
| Paiement → séquence → retrait manuel → clôture | Oui | Vraies machines T12/T13, CAN/STM32/IR/T04 simulés | Non | Testé par injection dans T01 ; assemblage réel bloqué |
| Facturation et clôture persistantes T04 | Contrat seulement | Double en mémoire | Non | Non : `integration_t04.py` retourne toujours `None` |
| Sécurité, table IR, ordre du trajet et adaptateur T13 réels | Contrats existants | Doubles explicites | Non | Non |

**La borne livrée ne déclenche pas de paiement ni de mouvement de retrait.**
Elle répond explicitement « facturation T04 non raccordée ». Même le mode
`ecran_tactile.py --simulation` conserve ce refus : son simulateur T11 existant
n'apporte pas toutes les confirmations requises par T12. Les partenaires du
banc ne sont injectés que par `test_t12_raccordement.py`.

Le lancement `./esa` et l'apparence de la console PC T13 ne changent pas.
`main.py` est l'ancien point d'entrée console RFID : cet incrément raccorde
l'écran tactile `interface/ecran_tactile.py`, pas une deuxième boucle CAN.

## Assemblage et responsabilités

- T01 fournit son `ServiceCAN`, son modèle de stationnement et son T11 existants
  à `PontT02Qt`. Aucun deuxième bus, lecteur ou fil de travail n'est créé.
- `application/integration_t12.py` est appelée **dans le travailleur Qt**, après
  la création de T04/T13. Elle retourne actuellement un raccordement indisponible.
  `RaccordementRetrait` est opérationnel avec les instances partenaires injectées.
- `demander_retrait(numero, id)`, `confirmer_retrait(id)` et `annuler_retrait(id)`
  sont asynchrones. Le retour immédiat du pont est une référence de requête,
  jamais un paiement réussi. `retrait_modifie(VueRetrait)` porte l'ID stable.
- Un nouveau billet saisi crée un UUID. Les répétitions gardent cet ID. Les
  notifications d'un ancien retrait sont ignorées par l'écran. Les anciens
  crochets T01 sans ID ne peuvent pas terminer le nouveau parcours.
- La confirmation ouvre le gel et les 60 secondes auprès de T04. Le précontrôle
  vérifie aussi les interverrouillages avant le gel. T12 revérifie toutes ses
  conditions après paiement avant de lancer la mécanique.
- `LecteurGardeRetrait` enveloppe le lecteur existant. Il appelle le garde T04
  avant chaque événement RFID accepté et le rappel de fin après T02. Un garde
  refusé ne transmet pas le badge à T02. Aucun changement à `Borne`, aux CSV de
  comptes ni à l'API T02 ; aucun second consommateur de résultats.
- Le contrat complémentaire `InterfaceGardePaiementRetrait` se trouve dans
  `api/retrait.py`. Le vrai T04 doit fournir ces deux rappels et la persistance
  des preuves ; l'implémentation du banc ne remplace pas cette livraison.
- Un reçu brut T02 ne déclenche ni mouvement ni message de réussite. Seul le
  statut T04 validé par T12 permet la suite. Un refus de carte laisse la fenêtre
  ouverte pour une nouvelle tentative intégrale, sans additionner les soldes.
- Annuler attend le résultat T04/T12 : si le débit est déjà validé, l'écran
  conserve le retrait. L'inactivité tactile ne prolonge ni ne remplace les 60 s.
- Une incertitude financière, un refus de départ après paiement ou une exception
  du raccordement interrompt le traitement sans réessai automatique. Une faute
  de commande ferme le travailleur et affiche l'intervention requise.
- La fermeture arrête T12 avant le lecteur, ferme ses journaux dans leur fil
  propriétaire et retire son abonnement CAN. T11 et les autres abonnés restent
  présents. Un redémarrage ne reprend pas une demande interrompue.

## Essais reproductibles — PC

Depuis le dossier du dépôt contenant cette branche :

```bash
QT_QPA_PLATFORM=offscreen ~/.venvs/esa-t13/bin/python -B -m unittest discover -s prog/tests -p 'test_t12*.py' -v
```

Attendu avec PyQt6 installé : **104 tests réussis, aucun ignoré**.
Dont 21 nouveaux essais de raccordement (8 sans Qt et 13 avec Qt).
Sans PyQt6, les 13 essais Qt sont ignorés : cela ne valide pas le raccordement.

Régression exécutée : **213 tests réussis, aucun ignoré**, avec Python 3.12,
PyQt6 6.10.0 et python-can 4.6.1 :

```bash
PYTHONPATH=prog/tests:prog/rpi:prog QT_QPA_PLATFORM=offscreen \
  ~/.venvs/esa-t13/bin/python -B -m unittest \
  test_t12_raccordement test_t12_retrait test_t12_paiement \
  test_interface_graphique test_interface_t04 test_comptes_transactions \
  test_t11_depot test_t13_service test_t13_service_mqtt test_t05_billets -q
```

Cas observés : cycle complet dans la vraie fenêtre T01, confirmation répétée,
ancien résultat ignoré, refus de carte puis nouvelle carte, badge à 60,000 s,
deux badges du même lot séparés par l'échéance, débit achevé hors délai,
annulation concurrente au paiement, contrôle avant débit, refus du départ sans
réessai, arrêt T13, mise hors service différée, erreur de journal et fermeture /
redémarrage du travailleur. Comptes et journaux sont temporaires.

## Ce qui bloque encore l'activation réelle

1. T04 réel : gel, gardes RFID, reçus et clôture persistants, avec un seul
   consommateur des résultats T02. `integration_t04.py` doit le construire.
2. Producteur réel de `ConditionsRetrait`, références/barrière vérifiées,
   correspondance des 14 IR et trajet de sortie validés. Le modèle T01 simulé
   « places absentes » et `conditions_confirmation() == True` ne sont pas des preuves.
3. Réponses IR réelles et fraîches au moment du départ : T12 demande désormais
   les états complets avant paiement et avant départ (voir LECTURE_IR_T12.md).
   T06 doit encore fournir les observations actuelles validées sur 0x302.
   Une synchronisation ne doit jamais être transformée en départ manuel.
4. Adaptateur T13 réel vers T03/T11/T12/sécurité, construit dans le même fil et
   relié à la supervision MQTT. Lui seul autorise les nouvelles demandes ; le
   raccordement vérifie aussi `EN_SERVICE` / `MISE_HORS_SERVICE`.
5. Dans `creer_module_t12`, construire les deux journaux et `GestionRetrait`
   avec ces partenaires, puis retourner `RaccordementRetrait`. Aucun simulateur
   ne doit être substitué dans la configuration matérielle.
6. Réconciliation des transactions interrompues et politique de renouvellement
   des séquences CAN (limite actuelle : 254 allocations sans réemploi).

Aucun essai de mouvement réel n'est demandé à cette étape.

Sources de contrats : interface individuelle T12 v1.3 (§9–11), protocole CAN
ESA v1.6, document maître v0.5 ; décisions mécaniques et limites détaillées dans
[ESSAIS_T12.md](ESSAIS_T12.md). Le contrat financier reste dans
[INTERFACE_T12_T04.md](INTERFACE_T12_T04.md). Les preuves exécutables sont dans
[`test_t12_raccordement.py`](../tests/test_t12_raccordement.py).
