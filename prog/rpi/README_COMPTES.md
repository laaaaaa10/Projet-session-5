# Comptes RFID preconfigures

Cette version ajoute deux comptes a la borne a partir d'un fichier CSV.
La troisieme carte reste absente du fichier pour tester le refus.

| Compte | ID UART complet | Numero imprime | Solde initial de demonstration |
| --- | --- | --- | --- |
| Jason Duval | `11008827F9` | `0008923129` | 20,00 $ |
| Lucia Caminos | `1100823734` | `0008533812` | 20,00 $ |

## Installation

L'archive contient les fichiers suivants a placer dans le depot existant :

- `prog/rpi/main.py` : remplacer la version envoyee pour cette modification.
- `prog/rpi/modules/gestion_comptes.py` : ajouter ce module.
- `prog/rpi/donnees/comptes.csv` : ajouter le fichier des deux comptes.
- `prog/rpi/README_COMPTES.md` : cette notice.

Conserver le module existant `prog/rpi/modules/lecteur_nfc_rfid.py` et les autres
fichiers du projet. L'archive est un ajout au projet, pas un projet autonome.
Elle utilise la fonction `numero_badge()` deja presente dans le lecteur.

Apres avoir telecharge l'archive dans `~/Downloads`, arreter la borne avec
Ctrl+C, puis executer :

```bash
cd ~/Projects/Projet-session-5
unzip -o ~/Downloads/comptes_rfid_jason_lucia.zip
sudo python3 prog/rpi/main.py
```

Les options existantes `--port`, `--gpio`, `--chip` et `--delai-ms` restent
disponibles. Si le projet tourne sur le Pi, copier ces fichiers dans son depot
avant d'y lancer la commande Python.

## Format du CSV

```csv
id_uart,nom,solde_centimes
11008827F9,Jason Duval,2000
1100823734,Lucia Caminos,2000
```

Les montants sont en centimes entiers : `2000` signifie 20,00 $, `550` signifie
5,50 $. Les 20,00 $ sont des valeurs de demonstration modifiables, pas des
montants imposes par le projet. Garder les virgules comme separateurs.

Le programme charge les comptes une fois au demarrage. Apres une modification
manuelle du CSV, redemarrer le programme. Il retrouve le fichier a partir du
chemin du module, quel que soit le repertoire depuis lequel il est lance.

## Comportement attendu

Au demarrage :

```text
BORNE | 2 comptes charges.
```

Pour Jason :

```text
BORNE | COMPTE RECONNU | Jason Duval | Numero de badge : 0008923129 | ID UART : 11008827F9 | Solde : 20,00 $
```

Pour Lucia :

```text
BORNE | COMPTE RECONNU | Lucia Caminos | Numero de badge : 0008533812 | ID UART : 1100823734 | Solde : 20,00 $
```

Pour toute autre carte, la ligne `BORNE` indique `REFUSE` et `Compte inconnu`.
L'identifiant de la troisieme carte n'a pas besoin d'etre inscrit : seuls les
deux ID complets du CSV sont reconnus.

La ligne `ACCEPTE` du lecteur signifie seulement que la lecture RFID est
valide. Une carte inconnue peut donc produire une lecture `ACCEPTE`, suivie
d'une ligne `BORNE | REFUSE`. La decision sur le compte se lit sur la ligne
`BORNE`.

L'identification utilise les dix caracteres de l'ID UART, jamais seulement le
numero imprime. Un autre prefixe avec les memes huit derniers caracteres
ne donne pas acces au meme compte.

Un CSV manquant, un ID mal forme ou duplique, un nom vide ou un solde invalide
arrete le programme avec un message `ERREUR`. Aucun compte n'est cree
automatiquement et le programme ne modifie pas le CSV.

Cette version reconnait le compte et affiche son solde. Elle ne realise encore
aucun paiement, debit, credit ou mouvement d'actionneur. La creation de compte
par interface et la verification du solde pour payer une commande restent des
etapes ulterieures.

## Verification sur le montage

1. Passer Jason : verifier le nom, le numero, l'ID complet et le solde.
2. Retirer sa carte et passer Lucia : verifier ses informations.
3. Retirer sa carte et passer la troisieme : verifier `BORNE | REFUSE`.
4. Garder chaque carte devant le lecteur : la logique de rearmement existante
   du module RFID continue de controler les lectures transmises a la borne.

Les essais logiciels du correctif utilisent un lecteur simule. La verification
physique reste a faire sur le montage.

## Origine des donnees

Les deux identifiants et les numeros de badge ont ete fournis dans la
conversation du 24 novembre 2026. Le point de depart est le `main.py` fourni
par l'utilisateur. Les noms Jason Duval et Lucia Caminos ont ete confirmes
sur le site officiel de Rockstar :
https://www.rockstargames.com/VI/only-in-leonida/jason
