# Accès de T13 aux comptes de T02

T13 reçoit les commandes du PC par MQTT. T02 reste responsable des comptes,
des montants en centimes et de la persistance. Cet accès Python local est prêt
à être fourni au responsable de T13 ; le transport MQTT et l'application PC
restent à brancher dans son module.

## Contrat public

Importer `InterfaceComptes`, `ResultatOperation`, `StatutOperation`,
`ConflitTransaction` et `ErreurStockage` depuis `api.comptes`.
La version du contrat est `VERSION_INTERFACE = 1`.
Son import ne nécessite ni lecteur, ni bibliothèques GPIO, ni stockage Linux.
L'implémentation CSV, elle, s'exécute sur Linux.

| Besoin de T13 | Appel | Retour |
| --- | --- | --- |
| `CONSULTER_SOLDE` | `consulter_solde(id_uart)` | Entier en centimes ; `None` pour un compte inconnu |
| `AJOUTER_CREDIT` | `ajouter_credit(id_transaction, id_uart, montant_centimes)` | `ResultatOperation` persistant |
| Synchroniser les soldes | `lister_soldes()` | Copie `{id_uart: solde_centimes}` des soldes courants |
| Retrouver une réponse après interruption | `retrouver_resultat_credit(id_transaction)` | Résultat enregistré ; `None` si cet ID est absent |

Un solde de `0` désigne un compte connu : tester `is None`, pas `if not solde`.
Les clés sont les **dix caractères de l'ID UART complet**, par exemple
`11008827F9`, jamais le nom ni le numéro décimal imprimé sur la carte.
Les noms d'affichage ne sont pas transmis dans cet accès.

L'accès ne propose ni débit ni création de compte. T13 passe par ces méthodes
et ne modifie jamais directement `comptes.csv` ou `operations.csv`.
Les topics MQTT, enveloppes de messages et règles de corrélation réseau
relèvent du contrat de T13 ; ce document n'en définit pas de nouveaux.

## Crédit et répétition d'une commande

Un crédit exige un entier strictement positif, en centimes : `500` ajoute
5,00 $. Les flottants, chaînes, booléens, montants nuls ou négatifs sont rejetés.

T13 attribue l'ID **avant le premier envoi** et le conserve après une réponse
perdue, une reconnexion ou un redémarrage. Il ne doit pas générer un nouvel ID
à chaque réception MQTT. Une nouvelle recharge volontaire reçoit un nouvel ID.
Les ID sont communs aux crédits et aux paiements : choisir des références
uniques, par exemple avec le préfixe `t13:credit-` et une valeur persistante
ou un UUID. La forme acceptée est `[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}`.

```python
# L'objet comptes est fourni au module T13 lors de son assemblage.
resultat = comptes.ajouter_credit("t13:credit-001", "11008827F9", 500)

# Une retransmission conserve exactement l'ID, la carte et le montant.
reprise = comptes.ajouter_credit("t13:credit-001", "11008827F9", 500)
assert reprise.deja_traitee is True

solde_courant = comptes.consulter_solde("11008827F9")
```

`ResultatOperation` contient l'ID de transaction, la date UTC, le type,
l'ID UART, le montant, le statut, les soldes avant/après et `deja_traitee`.

| Résultat ou erreur | Sens pour T13 |
| --- | --- |
| `CREDITE` | Crédit enregistré ; `succes=True` |
| `COMPTE_INCONNU` | Refus enregistré ; aucun compte créé, soldes du résultat à `None` |
| `deja_traitee=True` | Résultat déjà enregistré, aucun nouveau mouvement |
| `ValueError` | Paramètres invalides ; corriger la commande |
| `ConflitTransaction` | ID réutilisé pour une autre carte, un autre montant ou un paiement |
| `ErreurStockage` | Incident de fichier ; ne pas annoncer un refus de compte ni un crédit réussi |

Après `ErreurStockage`, le journal peut déjà contenir le résultat. Reprendre
avec **le même ID et les mêmes paramètres**, ou consulter le résultat durable.
Changer l'ID risquerait un second crédit. Un refus est lui aussi mémorisé.

Le solde du reçu est **historique** : il reste celui de cette opération même si
un paiement a eu lieu depuis. Utiliser `consulter_solde()` ou `lister_soldes()`
pour rafraîchir le PC. `retrouver_resultat_credit()` ne consomme aucune file et
rejette l'ID d'un paiement ; il ne prend pas les résultats destinés à T04.

## Branchement du futur module

`main.py` construit un seul `ServiceComptes` partagé avec T03 et T04 et fournit
`AccesComptes` à `application/integration_t13.py`.
Pour brancher le futur module, adapter uniquement cette fabrique, par exemple :

```python
from api.comptes import InterfaceComptes, ModuleT13

def creer_module_t13(comptes: InterfaceComptes) -> ModuleT13:
    from modules.supervision import SupervisionT13  # futur module du responsable
    return SupervisionT13(comptes=comptes)
```

Le module doit fournir `actualiser()`. La boucle de borne l'appelle après T03
et T04. Cette méthode traite les commandes disponibles puis rend la main :
aucune attente de connexion ou de réponse réseau dans la boucle RFID.
Une file entre les callbacks MQTT et `actualiser()` peut être gérée dans T13.
Les accès CSV restent synchrones et peuvent prendre le temps d'une écriture.

La fabrique livrée retourne `None` jusqu'à ce que le vrai module soit prêt.
Elle ne lance aucun client MQTT et n'applique aucun crédit automatiquement.
T13 valide les commandes reçues et leur accès côté réseau ; cet objet local
ne fournit pas d'authentification MQTT.

## Démonstration et vérification

Depuis la racine du dépôt, sur PC Linux ou Pi, sans sudo :

```bash
python3 -B prog/rpi/outils/demo_interface_t13.py
python3 -B -m unittest discover -s prog/tests -p 'test_interface_t13.py' -v
```

La démo utilise des fichiers temporaires : Jason passe de 2000 à 2500 centimes
une seule fois, la répétition renvoie `deja_traitee=True`, le changement de
montant avec le même ID est refusé et la carte inconnue reste sans compte.
Les tests vérifient aussi le partage des soldes entre T03/T04/T13 dans le vrai
programme principal avec un seul lecteur simulé.

Source du périmètre : *ESA_Document_maitre_responsabilites_T01_T13_v0.5*,
sections T02 et T13 (`CONSULTER_SOLDE`, `AJOUTER_CREDIT`, anti-doublons).
Les signatures Python ci-dessus sont le contrat local de cette implémentation.
