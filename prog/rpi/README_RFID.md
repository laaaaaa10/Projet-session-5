# Integration du lecteur RFID

Le programme principal ouvre le lecteur et appelle `lire()` dans sa boucle.
Un evenement `ACCEPTE` transmet l'identifiant a `traiter_badge()` dans `main.py`.
Pour cette etape, cette fonction affiche l'identifiant recu. La gestion des
comptes et transactions reste a implementer.

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

## Copier la version modifiee depuis le PC vers le Pi

Depuis la racine du depot sur le PC, la liaison Ethernet connue est utilisee :

```bash
ssh etudiant@10.42.0.201 'mkdir -p ~/esa-rfid-test'
scp -r prog/rpi etudiant@10.42.0.201:~/esa-rfid-test/
ssh -t etudiant@10.42.0.201 'sudo python3 ~/esa-rfid-test/rpi/main.py'
```

Cette copie est destinee au test sur le Pi. Les fichiers sources du projet
restent dans le depot Git du PC.

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

## Verification logicielle sur PC

```bash
python3 -m unittest discover -s prog/tests -p 'test_rfid_integration.py' -v
```

25 tests simules couvrent la reception progressive, les trames invalides, le
rearmement, le demarrage avec un badge present, le choix explicite de gpiochip0,
les erreurs materielles, la liberation des ressources et l'appel de
`traiter_badge()` uniquement pour `ACCEPTE`.

## Verification sur le montage

1. Lancer `main.py` sans badge : la configuration doit afficher gpiochip0.
2. Presenter un badge : une ligne `ACCEPTE` et une ligne `BORNE | Identifiant
   recu` doivent apparaitre pour cette lecture.
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
