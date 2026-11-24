# Comptes RFID preconfigures

Cette version ajoute deux comptes a la borne a partir d'un fichier CSV.
La troisieme carte reste absente du fichier pour tester le refus.

| Compte | ID UART complet | Numero imprime | Solde initial de demonstration |
| --- | --- | --- | --- |
| Jason Duval | `11008827F9` | `0008923129` | 20,00 $ |
| Lucia Caminos | `1100823734` | `0008533812` | 20,00 $ |

## Organisation des modules

- `modules/lecteur_nfc_rfid.py` recoit les trames, verifie leur checksum et
  gere le rearmement. Il definit aussi `numero_badge()`, utilise pour
  l'affichage decimal des identifiants valides.
- `modules/gestion_comptes.py` charge et valide les deux comptes du CSV.
- `main.py` relie une lecture valide a son compte et affiche le resultat.
- `donnees/comptes.csv` contient les donnees modifiables des comptes.

La conversion du numero de badge est definie une seule fois dans le module
RFID. Le module de comptes utilise uniquement l'ID complet comme cle.

## Installation et mises a jour

Tester et commiter les modifications sur le PC, puis les pousser sur la
branche `integration-rfid`. Le Pi recupere cette meme branche par Git.
Voir [README_RFID.md](README_RFID.md#mettre-a-jour-le-pi-par-git) pour les
commandes du premier clonage et des mises a jour.

Apres une mise a jour reussie, lancer sur le Pi :

```bash
cd ~/Projects/Projet-session-5
sudo python3 prog/rpi/main.py
```

Les options existantes `--port`, `--gpio`, `--chip` et `--delai-ms` restent
disponibles. Arreter avec Ctrl+C avant de mettre a jour ou relancer la borne.

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
La troisieme carte relevee, `1100880F2D`, reste absente du CSV : seuls les
deux ID complets de Jason et Lucia sont reconnus.

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

## Verification logicielle puis sur le montage

Depuis la racine du depot, sur le PC :

```bash
python3 -B -m unittest discover -s prog/tests -p 'test_rfid_integration.py' -v
```

Cette suite exerce les vrais modules RFID et comptes, avec l'UART et le GPIO
simules. Elle verifie les trois cartes, les numeros affiches, le refus d'un
autre ID complet ayant le meme numero affiche et l'absence de modification
du CSV. La fermeture des ressources est aussi verifiee.

Sur le montage :

1. Passer Jason : verifier le nom, le numero, l'ID complet et le solde.
2. Retirer sa carte et passer Lucia : verifier ses informations.
3. Retirer sa carte et passer la troisieme : verifier `BORNE | REFUSE`.
4. Garder chaque carte devant le lecteur : la logique de rearmement existante
   du module RFID continue de controler les lectures transmises a la borne.

Les essais logiciels ne remplacent pas cette verification physique.

## Origine des donnees

Les deux identifiants et les numeros de badge ont ete fournis dans la
conversation du 24 novembre 2026. Le point de depart est le `main.py` fourni
par l'utilisateur. Les noms Jason Duval et Lucia Caminos ont ete confirmes
sur le site officiel de Rockstar :
https://www.rockstargames.com/VI/only-in-leonida/jason
