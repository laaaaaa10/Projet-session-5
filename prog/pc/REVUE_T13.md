T13 ne possédait pas de transport MQTT ni d'application PC. Ce premier jalon
permet la consultation et le crédit via le vrai accès public T02, avec des
demandes conservées côté PC avant envoi, des réponses corrélées et une reprise
sans double crédit après coupure ou redémarrage.

La fenêtre PC indique la déconnexion et la péremption des données. Les modules
absents sont annoncés indisponibles : les 14 places restent inconnues et les
quatre commandes système sont refusées. Aucun état mécanique ni transaction
T04 n'est simulé comme réel. Les huit topics `esa/Equipe_N/...` et le champ
`id_commande` suivent l'interface T13 fournie. Les états sont publiés sur leurs
quatre sujets, avec une session/révision commune pour éviter les mélanges.
Les autres champs JSON et l'extension `SYNCHRONISER` restent une proposition
à valider par l'équipe. Aucune authentification n'est exigée par l'énoncé T13.

Validation du 25 novembre après synchronisation avec main à 0ccfd7f :
150 tests réussis, aucun ignoré. Les ajouts T03 et STM32 récents sont conservés.
Cela comprend les 122 tests existants, 22 tests T13 avec transport simulé et six tests avec
un broker Mosquitto 2.0.21 local réel, dont la fenêtre PC Qt et le raccordement au travailleur
Qt T02 et l'isolation des équipes 1 à 5. Les sorties fournies par l'utilisateur
valident aussi la connexion et l'abonnement MQTT de chaque appareil (PC et Pi)
au broker du cours. Les échanges applicatifs PC/T02 sur le Pi, la coupure
Wi-Fi réelle et les commandes de service/CAN restent à valider ou à raccorder.
Les soldes actifs et le modèle T02 ne sont pas modifiés par les essais.

Voir `prog/pc/README.md` et `prog/commun/t13/CONTRAT_MQTT_PROPOSE.md` pour le
périmètre, les paramètres manquants, les commandes PC/Pi et les essais suivants.
