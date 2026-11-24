# Accès T03 → T02 — version 1

T02 fournit à T03 les cartes lues et les soldes. Le responsable de T03 développe
la réservation, ses pages d'écran, les temporisations et la barrière. Ce contrat
prépare seulement son accès aux informations de T02.

## Deux méthodes disponibles

Le module T03 reçoit un objet `identification` de type `InterfaceIdentification`.
La borne construit cet objet et continue de posséder l'unique lecteur RFID.

```python
from api.identification import InterfaceIdentification, IdentificationCarte, ErreurStockage
```

| Méthode | Résultat |
| --- | --- |
| `identification.lire_identifications()` | Liste des nouvelles lectures ; retire ces éléments de la file T03 |
| `identification.consulter_solde(id_uart)` | Solde courant en centimes, ou `None` si la carte n'a pas de compte |

Chaque `IdentificationCarte` contient :

| Champ ou propriété | Sens |
| --- | --- |
| `id_uart` | Identifiant complet sur dix caractères hexadécimaux |
| `solde_centimes` | Solde au moment de la lecture, ou `None` si compte inconnu |
| `compte_connu` | `True` si le compte existe, y compris avec un solde de zéro |

Les objets reçus sont immuables. Le solde d'une ancienne lecture est un
instantané : utiliser `consulter_solde()` pour obtenir un solde plus récent.
Utiliser `compte_connu` ou `solde is not None` ; **zéro n'est pas une carte inconnue**.
La clé est l'ID UART complet, pas le numéro décimal imprimé ni un nom d'affichage.

Cet objet public ne propose ni crédit ni débit. La consultation ne prouve pas
qu'une carte est physiquement présente : seules les notifications proviennent
du parcours de lecture validé. T03 reste responsable de décider quand il attend
une identification et de vérifier ses autres conditions de réservation.

## Exemple côté T03

Un client exécutable est fourni dans `exemples/client_t03.py`. Le futur module
du collègue peut utiliser cette forme :

```python
from api.identification import InterfaceIdentification

class ReservationT03:
    def __init__(self, identification: InterfaceIdentification):
        self.identification = identification
        self.attend_une_carte = False

    def actualiser(self):
        for lecture in self.identification.lire_identifications():
            if not self.attend_une_carte:
                continue
            if lecture.compte_connu:
                # T03 utilise lecture.id_uart et lecture.solde_centimes.
                pass
            else:
                # T03 affiche son message de carte inconnue.
                pass
```

Ce bloc illustre les appels, pas une implémentation de la réservation.
`actualiser()` est déjà appelée par la boucle commune. Elle doit rendre la main
rapidement, sans boucle infinie, `input()` ni attente de carte.

**T03 vide sa file à chaque passage**, même lorsque son écran n'attend pas de
carte ; il ignore alors les lectures. Cela évite de réutiliser une ancienne
présentation lors de l'ouverture de l'écran. La file est en mémoire, sans
persistance ni limite automatique ; le client doit la consommer régulièrement.
Un seul consommateur doit lire cette file : le contrôleur T03, qui transmet
ensuite les informations à ses pages d'écran.

## Branchement préparé

Le seul point à compléter lorsque le collègue livre son code est
`application/integration_t03.py`. Par exemple, si son fichier est
`modules/reservation.py` et sa classe `ReservationT03` :

```python
def creer_module_t03(identification):
    from modules.reservation import ReservationT03
    return ReservationT03(identification=identification)
```

Les noms de ce futur module et de sa classe sont des exemples à adapter.
Le programme assemble déjà cet accès, et la boucle appelle déjà `actualiser()`.
La fonction retourne actuellement `None` : T03 reste désactivé jusqu'à son
branchement. Aucune file T03 n'est alimentée par le lancement normal tant
qu'aucun module T03 n'est branché.

Le client T03 n'ouvre ni UART ni GPIO et ne lit pas les CSV directement.
Il ne doit pas construire sa propre instance du lecteur ou du service de comptes.

## Lectures et séparation avec T04

- Seuls les événements RFID `ACCEPTE`, après validation du format et du
  checksum, peuvent fournir une identification. `IGNORE` et `INVALIDE` ne sont
  jamais transmis à T03. Le réarmement existant reste celui du lecteur unique.
- Hors demande de paiement, une lecture valide est transmise à T03 avec le
  solde du compte, ou avec `compte_connu=False` si la carte est inconnue.
- Lorsqu'une demande T04 attend une carte, cette lecture sert au paiement et
  n'est pas transmise à T03, même si le paiement est refusé.
- La file T03 et la file des résultats T04 sont distinctes : lire les
  identifications ne consomme aucun résultat de paiement.
- Une fois la tentative de paiement terminée, une nouvelle lecture acceptée
  peut de nouveau être transmise à T03. Le client doit toujours vérifier que
  son écran attend une carte avant de l'utiliser.

Une identification n'est ni un paiement, ni une réservation, ni une permission
d'ouverture de la barrière. Ces décisions restent dans leurs modules respectifs.
Ce contrat est une API Python dans le même programme ; il ne définit pas de
protocole réseau et ne réserve pas une session exclusive au module T03.

## Erreurs et redémarrage

Un ID mal formé fourni à `consulter_solde()` provoque `ValueError`.
Un fichier indisponible ou incohérent provoque `ErreurStockage` ; cette erreur
ne doit pas être présentée comme une simple carte inconnue. Aucun faux résultat
d'identification n'est ajouté à la file si la lecture du compte échoue.

Les soldes restent persistants via T02. Les notifications d'identification sont
éphémères : après un redémarrage, il faut présenter la carte à nouveau. Une
notification indique une lecture passée, pas une présence continue devant le lecteur.

## Vérification sans matériel

Depuis la racine du dépôt, sur le PC Linux ou le Pi, sans sudo :

```bash
python3 -B prog/rpi/outils/demo_interface_t03.py
python3 -B -m unittest discover -s prog/tests -p 'test_*.py' -v
```

La démo utilise des données temporaires et des événements RFID simulés. Elle
affiche les deux cartes connues et la carte inconnue, puis vérifie qu'un paiement
simulé produit un résultat T04 et aucune lecture T03. La consultation finale
voit le nouveau solde. Aucun solde actif n'est modifié et aucun actionneur n'est piloté.

Le contrat et le client d'exemple s'importent sans bibliothèque matérielle.
La démo avec stockage réel utilise Linux/Python 3.10+.

## Références

- Document maître ESA T01–T13, version 0.5, page 2 : T02 fournit la lecture et
  les soldes à T03. Les responsabilités de réservation et de barrière sont décrites
  dans la section T03 du même document.
- Base de cette évolution : commit `e9571f2`, branche `integration-rfid`.
- Contrat : `api/identification.py` ; accès : `application/acces_identification.py`.
- Vérification : `../tests/test_interface_t03.py`, plus les tests RFID, comptes et T04.
