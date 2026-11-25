# Vérification finale de T02

Ces essais complètent les tests logiciels avec le vrai lecteur. Ils utilisent
un dossier d'essai distinct qui reste disponible entre les lancements.
Les résultats indiqués sont les **résultats attendus**, à comparer au Pi.

## 1. Vérification logicielle sur le PC

Depuis `~/Projects/Projet-session-5` :

```bash
python3 -B -m unittest discover -s prog/tests -p 'test_*.py' -v
python3 -B prog/rpi/outils/demo_interface_t13.py
python3 -B prog/rpi/outils/demo_recuperation_comptes.py
```

La première démo crédite Jason une seule fois malgré deux appels identiques :
solde final **2500 centimes**, Lucia **2000**. La seconde reproduit un état
interrompu uniquement dans des fichiers temporaires. Elle doit afficher
`STOCKAGE | RECUPERATION CSV`, `2000 -> 1500 centimes`, puis
`deja_traitee=True` et un solde final de **1500 centimes**.

Cela valide la reprise logicielle, pas une coupure électrique du matériel.

## 2. Préparer le Pi et le dossier d'essai

Après le push depuis le PC, arrêter tout lecteur en cours avec **Ctrl+C**.
`Ctrl+Z` suspend le programme et peut garder le GPIO occupé.

```bash
cd ~/Projects/Projet-session-5 &&
git switch integration-rfid &&
git pull --ff-only origin integration-rfid
```

Dans ce même terminal, créer le dossier **une seule fois pour ce parcours** :

```bash
T02_VALIDATION="$(mktemp -d "$HOME/validation-t02.XXXXXX")"
printf '%s\n' "$T02_VALIDATION"
sudo python3 prog/rpi/outils/comptes.py --donnees "$T02_VALIDATION" consulter
```

Noter le chemin affiché pour le retrouver après une fermeture du terminal ou
un redémarrage. Les deux comptes doivent commencer à **20,00 $**.
Toutes les commandes suivantes doivent conserver `--donnees "$T02_VALIDATION"`.

## 3. Crédit et retransmission

Exécuter cette commande **deux fois à l'identique** :

```bash
sudo python3 prog/rpi/outils/comptes.py --donnees "$T02_VALIDATION" crediter \
  --id-transaction validation-credit-001 \
  --id-uart 11008827F9 --montant-centimes 500
```

Attendu : `CREDITE`, Jason **25,00 $**. La seconde exécution annonce un résultat
déjà enregistré et aucun nouveau mouvement. Lucia reste à **20,00 $**.

## 4. Refus puis autre carte pour la même somme

Retirer les cartes avant chaque lancement. Lancer cette demande, puis présenter
**Lucia**, numéro imprimé `0008533812` :

```bash
sudo python3 prog/rpi/outils/simuler_t04.py --donnees "$T02_VALIDATION" \
  --id-transaction validation-facture-001-tentative-1 --montant-centimes 2200
```

Attendu : `SOLDE_INSUFFISANT`, Lucia reste à **20,00 $**, sans débit partiel.
Le simulateur termine avec le code `2`, normal pour ce refus.

Faire une **nouvelle tentative**, avec un nouvel ID, puis présenter **Jason**,
numéro imprimé `0008923129` :

```bash
sudo python3 prog/rpi/outils/simuler_t04.py --donnees "$T02_VALIDATION" \
  --id-transaction validation-facture-001-tentative-2 --montant-centimes 2200
```

Attendu : `PAIE`, Jason passe de **25,00 $ à 3,00 $**. Lucia reste à **20,00 $**.
Une seule carte a payé les 22,00 $ en entier.

**Relancer exactement la seconde commande** : le résultat enregistré revient
sans demander de badge, sans ouvrir le lecteur et sans autre débit.
Réutiliser l'ID de la première tentative aurait seulement retrouvé son refus.

## 5. Carte inconnue

```bash
sudo python3 prog/rpi/outils/simuler_t04.py --donnees "$T02_VALIDATION" \
  --id-transaction validation-inconnue-001 --montant-centimes 500
```

Présenter le badge `0008916781` (`1100880F2D`). Attendu : `COMPTE_INCONNU`,
aucun compte créé et aucun solde modifié. Le code de sortie `2` est normal.

## 6. Journal et persistance

```bash
sudo python3 prog/rpi/outils/comptes.py --donnees "$T02_VALIDATION" consulter
sudo cat "$T02_VALIDATION/operations.csv"
```

Attendu : Jason **300 centimes**, Lucia **2000 centimes**. Si les étapes ont été
suivies une fois dans le dossier neuf, le journal contient quatre opérations
après son en-tête :

| ID | Type | Montant | Statut |
| --- | --- | --- | --- |
| `validation-credit-001` | CREDIT | 500 | CREDITE |
| `validation-facture-001-tentative-1` | PAIEMENT | 2200 | SOLDE_INSUFFISANT |
| `validation-facture-001-tentative-2` | PAIEMENT | 2200 | PAIE |
| `validation-inconnue-001` | PAIEMENT | 500 | COMPTE_INCONNU |

Chaque commande a déjà relancé le service dans un nouveau processus. Pour
vérifier aussi un **redémarrage complet du Pi**, conserver le chemin du dossier,
redémarrer proprement le Pi, puis le remettre dans la variable :

```bash
cd ~/Projects/Projet-session-5
# Remplacer ce chemin par celui réellement noté à l'étape 2.
T02_VALIDATION='/home/etudiant/validation-t02.REMPLACER'
sudo python3 prog/rpi/outils/comptes.py --donnees "$T02_VALIDATION" consulter
sudo cat "$T02_VALIDATION/operations.csv"
```

Attendu : les mêmes soldes et quatre opérations. Ne pas relancer `mktemp`
pour cette vérification, car cela créerait un autre dossier neuf.

## 7. Lecture et buzzer

Reprendre la consultation habituelle avec `sudo python3 prog/rpi/main.py`.
Présenter les cartes, garder une carte devant le lecteur, puis la retirer
et la représenter après au moins 500 ms : vérifier une seule action par
présentation acceptée. La consultation seule ne débite rien.

Écouter aussi le buzzer du lecteur pendant les présentations. Il doit fonctionner
de façon autonome ; T02 ne pilote aucune sortie de buzzer. Ce point nécessite
une observation sur le montage et ne peut pas être validé par les tests PC.

## Correspondance avec la liste T02

| Attendu | Vérification disponible |
| --- | --- |
| Lecture UART ASCII | Lecteur réel + tests RFID |
| Rejet des trames incomplètes/invalides | Tests de délimiteurs, checksum et expiration |
| Carte maintenue, réarmement | Étape 7 + tests RFID |
| Comptes préconfigurés par identifiant | Modèle CSV ; clé interne = ID UART complet |
| Soldes et journal persistants | Étape 6 |
| Consultation, crédit, débit en centimes | Étapes 2 à 6 |
| Une carte couvre tout, aucun débit partiel/négatif | Étape 4 + tests de validation |
| ID stable, aucun crédit/débit doublé | Étapes 3, 4 et 6 |
| Erreurs et incohérences de fichier signalées | Tests stockage + démo de récupération |
| Accès T03, T04 et T13 | Contrats `api/` et tests des trois interfaces |
| Buzzer autonome | Observation physique à l'étape 7 |

Les alias Jason et Lucia sont conservés pour l'affichage selon le choix du
projet ; ils ne servent pas de clés de compte. Le document maître demande
des comptes sans noms : ces alias restent un écart à cette formulation.

Sources : liste de contrôle T02 fournie le 24 novembre 2026 ;
*ESA_Document_maitre_responsabilites_T01_T13_v0.5*, sections T02 et T13 ;
contrats et tests du présent dépôt. Les tests logiciels ne remplacent pas
les observations matérielles demandées ci-dessus.
