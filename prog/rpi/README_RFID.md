# Integration du lecteur RFID

Le programme principal ouvre le lecteur et appelle `lire()` dans sa boucle.
Un evenement `ACCEPTE` transmet l'identifiant a `traiter_badge()` dans `main.py`.
Cette fonction recherche le compte dans `donnees/comptes.csv` et affiche son
nom et son solde, ou refuse la carte inconnue. La transaction reste a implementer.
Voir [README_COMPTES.md](README_COMPTES.md) pour les comptes preconfigures.

## Configuration du montage teste

| Parametre | Valeur |
| --- | --- |
| Plateforme | Raspberry Pi Compute Module 5 |
| Lecteur | ID Innovations ID-12LA, mode ASCII |
| UART | `/dev/ttyAMA0`, 9600 bauds, 8N1 |
| Presence RNG | BCM GPIO17, active a l'etat haut |
| Controleur GPIO | `gpiochip0`, deja identifie sur ce montage |
| Rearmement du meme identifiant | 500 ms apres le retrait |

Les bibliotheques `serial` (pySerial), `gpiozero` et `lgpio` sont deja
disponibles sur le Pi. Elles sont importees seulement a l'ouverture du lecteur.
Il n'y a plus de recherche automatique des gpiochip : les alias gpiochip0
et gpiochip4 avaient rendu cette recherche ambigue sur ce CM5.

## Lancer depuis la racine du depot, sur le Pi

```bash
sudo python3 prog/rpi/main.py
```

Exemple de personnalisation :

```bash
sudo python3 prog/rpi/main.py --delai-ms 1000 --chip 0
```

Le test direct reste disponible avec les memes options :

```bash
sudo python3 prog/rpi/modules/lecteur_nfc_rfid.py
```

Un seul programme doit ouvrir le lecteur a la fois. Quitter avec Ctrl+C
libere l'UART, l'entree RNG et la fabrique GPIO, y compris en cas d'erreur.
Ctrl+Z suspend le processus : les ressources restent alors reservees.

## Mettre a jour le Pi par Git

Les modifications sont faites, testees et commitees dans le depot du PC.
Depuis ce depot, sur la branche `integration-rfid` :

```bash
git push -u origin integration-rfid
```

Sur le Pi, arreter le programme avec Ctrl+C, puis mettre a jour sa copie :

```bash
cd ~/Projects/Projet-session-5
git switch integration-rfid
git pull --ff-only origin integration-rfid
```

Une fois la mise a jour reussie, lancer `sudo python3 prog/rpi/main.py`.
Ne pas lancer en parallele l'ancienne copie `~/esa-rfid-test/rpi/main.py`.

Pour une premiere installation sur le Pi, apres le push depuis le PC :

```bash
mkdir -p ~/Projects
git clone --branch integration-rfid https://github.com/laaaaaa10/Projet-session-5.git ~/Projects/Projet-session-5
```

## Comportement conserve et correction au demarrage

- Verifier les 16 octets de la trame ASCII et le checksum XOR avant decision.
- Donner une seule decision par identifiant et par presentation.
- Pour le meme identifiant, compter les 500 ms depuis son dernier retrait.
- Refuser une representation trop rapide pendant toute cette presentation,
  meme si le badge reste ensuite assez longtemps dans la zone.
- Accepter un identifiant different sans attendre le delai du precedent.
- Conserver la presentation d'origine si le badge est retire pendant une trame.
- Correction : un badge deja present a l'ouverture doit effectivement etre
  retire puis represente avant de pouvoir etre accepte.

`lire()` retourne une liste d'objets `EvenementRFID` avec les champs `type`,
`message`, `identifiant` et `brut`. Les types sont `INFO`, `PRESENCE`, `RETRAIT`,
`ACCEPTE`, `IGNORE` et `INVALIDE`. La methode n'attend pas les 500 ms : l'UART
utilise `timeout=0`, les lectures sont limitees a 256 octets par passage et les
delais reposent sur une horloge monotone. Le programme principal repasse environ
toutes les 2 ms ; ce n'est pas une garantie temps reel de Linux. Les futurs
traitements CAN, MQTT et ecran devront laisser revenir cette boucle rapidement.

`ACCEPTE` signifie que la lecture est valide. L'autorisation d'un compte et la
commande d'un actionneur doivent etre decidees ensuite par la logique de borne.

## Numero de badge et identifiant complet

La fonction publique `lecteur_nfc_rfid.numero_badge(identifiant)` convertit
les huit derniers caracteres hexadecimaux d'un ID valide de dix caracteres
en un numero decimal complete sur dix chiffres. Elle est utilisee par
l'affichage des evenements RFID et par `main.py` ; il n'y a qu'une seule
implementation de cette conversion.

Les correspondances relevees sont `11008827F9` / `0008923129` pour Jason et
`1100823734` / `0008533812` pour Lucia. La troisieme carte relevee,
`1100880F2D`, doit produire `BORNE | REFUSE` puisqu'elle est absente du CSV.

Le numero decimal est uniquement un affichage. Le checksum, le rearmement
et la recherche de compte utilisent toujours l'ID UART complet.

## Verification logicielle sur PC

```bash
python3 -m unittest discover -s prog/tests -p 'test_rfid_integration.py' -v
```

Les tests couvrent la reception progressive, les trames invalides, le
rearmement, le demarrage avec un badge present, le choix explicite de gpiochip0,
les erreurs materielles, la liberation des ressources et l'appel de
`traiter_badge()` uniquement pour `ACCEPTE`.

Les tests de parcours utilisent le vrai `main.py`, le vrai module RFID et
le vrai chargeur CSV. Seuls l'UART, le GPIO et le temps sont simules. Les
trames des trois cartes passent donc par la reception, la verification du
checksum, le rearmement et la recherche du compte. La fonction `numero_badge()`
n'est pas remplacee par une simulation : son absence fait echouer ces tests.

## Verification sur le montage

1. Lancer `main.py` sans badge : la configuration doit afficher gpiochip0.
2. Presenter Jason ou Lucia : une ligne `ACCEPTE` puis `BORNE | COMPTE RECONNU`
   doivent afficher les bons numeros et le bon compte. La troisieme carte
   doit donner une lecture `ACCEPTE` suivie de `BORNE | REFUSE`.
3. Garder le badge : aucune nouvelle action de borne pour le meme identifiant.
4. Retirer et representer rapidement : `IGNORE`, sans nouvelle ligne `BORNE`.
5. Laisser ce badge refuse dans la zone : aucune acceptation differee.
6. Retirer, attendre au moins 500 ms puis representer : nouvelle acceptation.
7. Redemarrer le programme avec un badge deja present : retirer puis representer
   avant toute acceptation. Terminer avec Ctrl+C puis relancer pour verifier
   que les ressources ont ete liberees.

Les essais logiciels ne remplacent pas cette verification sur le Pi.

## Sources

- Code de test et configuration verifies sur le montage, fournis par l'etudiant.
- Fiche ID Innovations ID-2/12/20 LA, sections 4 et 6, dans la documentation du projet.
- [gpiozero : DigitalInputDevice](https://gpiozero.readthedocs.io/en/stable/api_input.html#digitalinputdevice).
- [gpiozero : LGPIOFactory](https://gpiozero.readthedocs.io/en/stable/api_pins.html#lgpio).
- [pySerial : API et timeout non bloquant](https://pyserial.readthedocs.io/en/latest/pyserial_api.html).
