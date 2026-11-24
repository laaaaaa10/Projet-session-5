# Interface T04 → T02 — version 1

L'interface logicielle est prête. T04 fournit **un ID de tentative et un montant
en centimes**, puis récupère un résultat. T02 s'occupe du lecteur, des comptes
et de l'enregistrement du paiement.

Ce contrat est local au même programme Python. Il ne définit pas un protocole
réseau. Le calcul des tarifs et la gestion des factures restent dans T04.

## Ce que le responsable T04 doit utiliser

Tous les imports du contrat viennent d'un seul module :

```python
from api.paiements import (
    DemandePaiement, InterfacePaiement, StatutOperation,
    PaiementEnCours, ConflitTransaction, ErreurStockage,
)
```

L'objet `paiements` est **fourni par la borne** au constructeur de T04.
`InterfacePaiement` décrit ses méthodes ; ce n'est pas un service à instancier.
T04 n'a pas à importer le lecteur, ouvrir le GPIO, charger un CSV ou calculer
l'ID de la carte.

| Méthode sur `paiements` | Retour | Utilisation |
| --- | --- | --- |
| `demander_paiement(DemandePaiement(id, montant))` | `None` | Demander le paiement ou rejouer une demande connue |
| `lire_resultats_paiement()` | Liste de `ResultatOperation` | Récupérer et retirer les notifications disponibles |
| `retrouver_resultat_paiement(id)` | Résultat ou `None` | Relire un résultat enregistré, notamment après redémarrage |
| `annuler_paiement(id)` | Booléen | Annuler une attente de carte encore non terminée |

`retrouver_resultat_paiement()` ne vide pas la file et ne débite rien.
`None` signifie « aucun résultat enregistré pour cet ID », pas « refusé ».
Une demande inconnue, en attente ou annulée peut donc retourner `None`.

## Exemple côté T04

Un exemple complet, importable et testé se trouve dans
[`exemples/client_t04.py`](exemples/client_t04.py). Il demande un paiement,
lit ses notifications et ignore les notifications répétées dans le même
processus. Il ne calcule aucun tarif et ne commande aucun actionneur.

Le futur module doit suivre cette forme :

```python
from api.paiements import DemandePaiement, InterfacePaiement, StatutOperation

class FacturationT04:
    def __init__(self, paiements: InterfacePaiement):
        self.paiements = paiements
        # Charger ici les factures et les tentatives que T04 conserve.

    def payer_facture(self, id_transaction: str, montant_centimes: int):
        # Conserver cet ID avec la facture AVANT de soumettre la demande.
        self.paiements.demander_paiement(
            DemandePaiement(id_transaction, montant_centimes)
        )

    def actualiser(self):
        for resultat in self.paiements.lire_resultats_paiement():
            if resultat.statut == StatutOperation.PAIE:
                # Enregistrer la facture payée, une seule fois par transaction.
                pass
            else:
                # Enregistrer/afficher le refus pour cette tentative.
                pass
```

Ce bloc montre les points à compléter dans T04 ; le client d'exemple fonctionne
déjà pour les démonstrations. Dans le vrai T04, la déduplication et l'état des
factures doivent être **persistants**. Le dictionnaire du client d'exemple ne
suffit pas à dédupliquer les actions de T04 après son propre redémarrage.

## Un seul point à modifier quand T04 sera prêt

Dans [`application/integration_t04.py`](application/integration_t04.py),
remplacer le `return None` par la création du vrai module. Par exemple,
si le collègue choisit le fichier `modules/facturation.py` et la classe
`FacturationT04` :

```python
def creer_module_t04(paiements):
    from modules.facturation import FacturationT04
    return FacturationT04(paiements=paiements)
```

Le programme principal appelle déjà cette fonction. La boucle de la borne
appelle déjà `t04.actualiser()` après les événements RFID de chaque passage.
**Aucune nouvelle boucle RFID et aucune modification supplémentaire de
`main.py` ne sont nécessaires.**

Pour l'instant, la fonction retourne `None` : aucun faux T04 n'est activé et
aucune demande automatique de paiement n'est créée.

`actualiser()` doit rendre la main rapidement : pas de `input()`, d'attente de
carte, de `sleep()` ou de boucle infinie dedans. La borne attend déjà 2 ms entre
ses passages. Les opérations de stockage sont synchrones et peuvent allonger
un passage ; ce n'est pas une garantie de temps réel.

Les méthodes de paiement protègent leur état par un verrou. **Un seul
consommateur, T04, vide la file de résultats.** L'écran doit recevoir les
résultats relayés par T04 plutôt que vider lui aussi cette file. Le simulateur
`simuler_t04.py` utilise cette file pour son propre essai et se lance séparément.

## Demande et résultat

L'ID contient de 1 à 128 caractères. Le premier est une lettre ASCII ou un
chiffre ; les suivants peuvent aussi être `_`, `.`, `:` ou `-`.
Exemple : `facture-42-tentative-1`.

Le montant est un entier en centimes, positif ou nul : `550` = 5,50 $.
Les flottants et booléens sont rejetés. Un paiement nul reste soumis à la
présentation d'une carte associée à un compte.

| Champ du résultat | Sens |
| --- | --- |
| `id_transaction` | ID de tentative fourni par T04 |
| `date_utc` | Date UTC du résultat initial |
| `type_operation` | `PAIEMENT` pour cette API |
| `id_uart` | ID complet de la carte utilisée |
| `montant_centimes` | Montant demandé |
| `statut` | `StatutOperation.PAIE`, `COMPTE_INCONNU` ou `SOLDE_INSUFFISANT` |
| `solde_avant_centimes` | Solde avant l'opération, ou `None` si compte inconnu |
| `solde_apres_centimes` | Solde après l'opération, ou `None` si compte inconnu |
| `deja_traitee` | `True` pour un résultat retrouvé ou retransmis |

Seul `PAIE` confirme le paiement. `ACCEPTE` est un événement du lecteur RFID
qui indique uniquement que sa trame est valide.

Un refus termine la tentative sans débit partiel. Passer ensuite une autre
carte consulte son compte tant que T04 n'a pas demandé une autre tentative.
Les soldes d'un résultat retransmis sont ceux du reçu initial, pas nécessairement
les soldes courants après d'autres opérations.

## Erreurs, retransmissions et annulation

| Situation | Comportement à respecter dans T04 |
| --- | --- |
| Une autre demande attend une carte | `PaiementEnCours` : conserver la nouvelle demande pour plus tard |
| Même ID réutilisé avec d'autres données | `ConflitTransaction` : corriger l'appel, ne pas ignorer l'erreur |
| Paramètre mal formé | `ValueError` (ou `TypeError` si l'objet demande n'est pas du bon type) |
| Stockage indisponible/incohérent | `ErreurStockage` : ne pas conclure « refusé », reprendre le même ID |
| Réponse perdue | Relire le résultat ou retransmettre exactement la même demande |
| Refus reçu puis nouvel essai volontaire | Créer un nouvel ID de tentative |
| Paiement reçu plusieurs fois | Appliquer les effets T04 une seule fois pour cet ID |

La déduplication T02 porte sur les **IDs de transaction**, pas les factures :
deux IDs distincts peuvent produire deux débits. T04 doit conserver l'association
entre facture et tentative, et ne pas demander de nouveau paiement pour une
facture déjà payée.

Les paiements et refus terminés sont persistants. La file de notifications et
les attentes sont en mémoire. Après redémarrage, T04 retrouve un résultat avec
`retrouver_resultat_paiement(id)`, ou soumet de nouveau sa demande avec le
même ID et le même montant. Une retransmission d'un résultat ancien ne remplace
pas une autre demande actuellement en attente.

`annuler_paiement(id)` retourne `True` uniquement si cette attente a été annulée.
`False` signifie qu'elle n'attendait plus, n'était pas l'attente courante, ou
était déjà enregistrée dans le journal. Aucun remboursement n'est effectué.
Après une erreur d'écriture, la borne consulte aussi le journal avant
d'annoncer une annulation ; si le paiement était enregistré, elle renvoie son
résultat au lieu de le masquer.

Une erreur de stockage ne prouve pas l'absence de débit. Si le journal a été
écrit avant l'erreur, reprendre le même ID permet de retrouver son résultat
sans nouvelle carte et sans second débit. Un ID de crédit n'est pas un ID de
paiement : sa recherche par cette API provoque `ConflitTransaction`.

L'annulation d'une attente n'est pas journalisée et ne réserve pas définitivement
son ID. T04 doit arrêter ses retransmissions après annulation et décider de
l'état de ses attentes après redémarrage.

## Essai immédiat sans Raspberry Pi

Sur le PC Linux, depuis la racine du dépôt, sans sudo :

```bash
python3 -B prog/rpi/outils/demo_interface_t04.py
python3 -B -m unittest discover -s prog/tests -p 'test_*.py' -v
```

La démonstration utilise le vrai stockage et le vrai service, dans un dossier
temporaire. Seuls les événements RFID sont simulés. Elle montre :

1. Jason paie 5,50 $ : 20,00 $ → 14,50 $.
2. Lucia refuse 25,00 $ avec son solde de 20,00 $.
3. La carte inconnue est refusée.
4. Une nouvelle instance de borne retrouve le paiement de Jason sans le répéter.

La démonstration ne touche pas les comptes actifs. Le contrat et le client
d'exemple sont importables sans bibliothèque matérielle ni `fcntl` ; le
stockage réel et cette démonstration nécessitent Linux/Python 3.10+.

Pour l'essai avec les vraies cartes, le simulateur existant reste disponible.
Voir [README_COMPTES.md](README_COMPTES.md).

## Références

- Base : commit `ec95816`, branche `integration-rfid`, confirmée sur le dépôt.
- Contrat : `api/paiements.py` ; implémentation : `application/borne.py`.
- Branchement : `application/integration_t04.py` et `main.py`.
- Vérification : `../tests/test_interface_t04.py` avec les suites comptes et RFID.
- Répartition des responsabilités : T04 calcule la facturation, comme confirmé
  par l'utilisateur ; T02 gère le paiement.
