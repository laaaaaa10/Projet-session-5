# Interface locale T04 → T02

T04 calcule le montant et décide quand demander un paiement. T02 identifie le
compte, contrôle son solde, enregistre l'opération et retourne son résultat.
T02 ne calcule aucun tarif et ne commande aucun actionneur.

Cette interface est un contrat Python utilisable dans le même programme.
La branche actuelle ne contient pas l'implémentation de facturation T04 :
son branchement réel reste à réaliser. Le simulateur teste déjà cette interface.

## Entrée et sortie

```python
from modeles.comptes import DemandePaiement, StatutOperation

# borne est l'instance Borne déjà créée pour le lecteur.
# Le montant vient du calcul de T04, jamais du badge.
borne.demander_paiement(DemandePaiement(
    id_transaction="facture-42-tentative-1",
    montant_centimes=550,
))

# À appeler dans le traitement périodique de T04, après les lectures RFID.
for resultat in borne.lire_resultats_paiement():
    if resultat.statut == StatutOperation.PAIE:
        # T04 enregistre la facture payée une seule fois par id_transaction.
        pass
    else:
        # Afficher le refus ou proposer une nouvelle tentative.
        pass
```

La boucle RFID existante se trouve dans `Borne.executer()`.
Pour l'intégration, le contrôleur commun peut appeler
`Borne.traiter_evenement(evenement)` pour les événements de
`LecteurRFID.lire()`, puis les traitements périodiques de T04.
Il faut conserver un seul propriétaire du lecteur ; ne pas lancer deux boucles
RFID indépendantes. Les méthodes de la borne protègent la demande en attente
par un verrou pour les appels provenant d'un autre fil d'exécution.

`demander_paiement()` retourne immédiatement après vérification du stockage.
Elle n'attend pas qu'un badge arrive. Une seule demande peut attendre un badge :
une autre demande déclenche `PaiementEnCours`. Répéter la même demande en
attente n'en crée pas une seconde. Un montant différent pour le même ID
déclenche `ConflitTransaction`.

Si l'ID correspond déjà à une opération terminée, son résultat est remis dans
la file de sortie sans demander un nouveau badge. Le montant et le type doivent
correspondre à l'opération enregistrée.

`lire_resultats_paiement()` retourne une liste et vide cette file en mémoire.
Si T04 perd une réponse ou redémarre, il peut redemander avec le même ID :
le résultat persistant reste dans le journal. T04 doit conserver ses propres
IDs de tentative et les associer à ses factures.

## Résultat

| Champ | Sens |
| --- | --- |
| `id_transaction` | ID de tentative fourni par T04 |
| `date_utc` | Date UTC du résultat initial |
| `type_operation` | `TypeOperation.PAIEMENT` |
| `id_uart` | ID complet de la carte utilisée |
| `montant_centimes` | Montant demandé |
| `statut` | `PAIE`, `COMPTE_INCONNU` ou `SOLDE_INSUFFISANT` |
| `solde_avant_centimes` | Solde avant cette opération, ou `None` si compte inconnu |
| `solde_apres_centimes` | Solde après cette opération, ou `None` si compte inconnu |
| `deja_traitee` | `True` si le résultat est une répétition d'une opération enregistrée |

Sur un résultat répété, les soldes sont ceux du reçu initial ; ils ne constituent
pas une nouvelle consultation du solde courant.

Seul `PAIE` confirme un paiement. `ACCEPTE` appartient au lecteur RFID et
confirme uniquement la validité d'une trame. Une carte inconnue ou un solde
insuffisant termine la tentative avec un refus, sans modifier les soldes.
La borne repasse ensuite en consultation tant que T04 n'a pas soumis une autre
demande. Pas de paiement partiel ni de cumul de plusieurs cartes.

## Identifiants et reprises

L'ID est une chaîne de 1 à 128 caractères. Le premier est une lettre ASCII ou un
chiffre ; les suivants peuvent aussi être `_`, `.`, `:` ou `-`.
Le montant est un `int` en centimes, positif ou nul, jamais un `float`.

- Réponse perdue ou erreur de stockage : reprendre **le même ID** et le même montant.
- Refus reçu, puis essai d'une autre carte ou après crédit : utiliser un **nouvel ID de tentative**.
- Paiement confirmé : T04 marque la facture payée ; il ne lance pas une autre
  tentative pour cette même facture.

La protection de T02 porte sur les IDs de transaction, pas sur les numéros
de facture : deux IDs différents constituent deux opérations différentes.
T04 doit également dédupliquer ses effets en aval (facture payée, demande de
retrait) lorsqu'il reçoit plusieurs fois le même résultat.

Une erreur de stockage remonte comme `ErreurStockage`, sans résultat de
paiement annoncé. Elle ne prouve pas que le débit n'a pas été enregistré :
le journal peut déjà contenir l'opération. Ne pas remplacer l'ID pour contourner
cette erreur. Un ID réutilisé avec un autre contenu provoque
`ConflitTransaction`, sans nouveau débit.

## Annulation et redémarrage

```python
annule = borne.annuler_paiement("facture-42-tentative-1")
```

Retourne `True` uniquement si cette demande attendait encore un badge.
Une demande terminée n'est ni annulée ni remboursée par cette méthode.
L'annulation d'une attente ne réserve pas définitivement son ID dans le journal ;
l'appelant doit donc arrêter ses retransmissions après annulation.
Les attentes et annulations restent en mémoire : après redémarrage, T04 décide
s'il doit soumettre de nouveau une attente. Les résultats terminés sont persistants.

## Accès métier sans lecteur

Pour un module local qui possède déjà l'ID UART validé :

```python
from modules.gestion_comptes import ServiceComptes
from stockage.comptes_csv import DepotComptesCSV

comptes = ServiceComptes(DepotComptesCSV())
compte = comptes.consulter_compte("11008827F9")
resultat = comptes.payer("facture-42-tentative-1", "11008827F9", 550)
```

Le service est une API interne de confiance : il ne prouve pas à lui seul la
présence physique de la carte. La borne appelle cette API seulement pour une
lecture `ACCEPTE`. `crediter(id_transaction, id_uart, montant_centimes)` suit
les mêmes règles de doublons, avec un montant strictement positif et le statut
`CREDITE`. Le crédit est destiné à la gestion locale des comptes de démonstration.

## Références du projet

- Base de cette évolution : commit `ab43d56`, branche `integration-rfid`.
- Répartition T04/facturation confirmée par l'utilisateur.
- Implémentation : `modeles/comptes.py`, `application/borne.py`,
  `modules/gestion_comptes.py` et `stockage/comptes_csv.py`.
- Vérification : `../tests/test_comptes_transactions.py` et
  `../tests/test_rfid_integration.py`.
