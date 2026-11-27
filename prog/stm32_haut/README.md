# STM32 HAUT : notes

Pas encore testé sur la carte : bras (drive_motor.c), ParkingHigh_Home / Store / Retrieve.

## Intégration (main.c)
```c
DriveMotor_Init();
ParkingHigh_Init(&hi2c1);   // une fois, après les MX_..._Init
ParkingHigh_Process();      // dans while(1)
```
Points d'entrée pour le CAN (bloquants, sauf IsBusy) : `ParkingHigh_Home()` (une fois avant le reste), `ParkingHigh_Store(case)`, `ParkingHigh_Retrieve(case)` (case 1 à 14), `ParkingHigh_IsBusy()`.

## Plateau et ascenseur (parking_high.c)
- Les valeurs qui changent (pas, Hz, pauses, timeout) sont écrites directement dans les appels, pas dans le .h.
- Plateau en demi-pas (MODE0 fermé sur le PCB-01) : 4000 pas = 1 tour = 8 secteurs de 45 degrés (7 emplacements + 1 secteur vide), donc 1 emplacement = 500 pas, à 400 Hz. pas = degrés x 4000 / 360.
- Le plateau tourne toujours en `STEPPER_HORAIRE`, en supposant que ce sens va de l'emplacement 1 vers 7, puis le secteur vide, puis 1.
- `Stepper_Rotate(&stepper_rotation, sens, pas, Hz)` : bloquant, avec rampe d'accélération.
- `go_to_floor(étage)` : monte ou descend (selon l'étage actuel) jusqu'au capteur de l'étage visé, 167 Hz, timeout 120 s. Étage inconnu (0) : descend. Si ça échoue, l'étage redevient inconnu et Store/Retrieve sont refusés jusqu'au prochain Home.
- Store : quai, bras `DRIVEMOTOR_ANTIHORAIRE` (rentre la voiture), étage, plateau, bras `DRIVEMOTOR_HORAIRE` (pousse la voiture dans l'emplacement). Retrieve : étage, plateau, bras `DRIVEMOTOR_ANTIHORAIRE`, quai, bras `DRIVEMOTOR_HORAIRE`.
- Sens à confirmer sur la carte : `STEPPER_HORAIRE` / `STEPPER_ANTIHORAIRE` (plateau et ascenseur) et `DRIVEMOTOR_HORAIRE` / `DRIVEMOTOR_ANTIHORAIRE` (bras), directement dans les appels.
- Hypothèses à confirmer avec l'équipe :
  - case 1 à 7 = étage 2, case 8 à 14 = étage 3 (étage 1 = quai), emplacements 1 à 7 (`space_to_floor_slot`) ;
  - plateau sans capteur : position suivie en logiciel, emplacement 1 au démarrage ;
  - bras : 4,5 s à 80 % pour une course (estimé avec les specs du vérin, pas mesuré).

## Moteurs pas-à-pas (stepper_motor.c)
- Jeux de broches (STEP / DIR), choisis en haut du .c avec `STEPPER_ROTATION_PINS` (2) et `STEPPER_HEIGHT_PINS` (1) :

| Jeu | STEP | DIR | Note |
|---|---|---|---|
| 0 | PB14 | PC8 | en panne, ne pas utiliser |
| 1 | PB0 (TIM3 CH3) | PC4 | hauteur : P11 pin 4 / pin 1 |
| 2 | PA2 (TIM5 CH3) | PB5 | rotation : STEP sur P11 pin 2, DIR sur P9 pin 1, en direct |

- P11 (PMOD UART) : pin 1 = PC4, pin 2 = PA2, pin 3 = PA3, pin 4 = PB0. Les jeux 1 et 2 sont configurés par le .c (rien à faire dans CubeMX). Broches mortes connues : PB1, PD2, PB14, PC8. Autres broches libres : P9 = PB5 / PB7 / PC11 / PA15 (pins 1 à 4), à changer avec `SET2_DIR_PORT` et `SET2_DIR_PIN` en haut de stepper_motor.c.
- Rampe : `STEPPER_START_HZ` (60) et `STEPPER_RAMP_MS` (800), en haut du .c. Si un moteur cale : baisser la fréquence demandée ou `STEPPER_START_HZ`, ou allonger `STEPPER_RAMP_MS`.
- Drive PCB-01 : pas de potentiomètre de courant (Vref fixe, le courant est fixé par le moteur, environ 0,35 A). Les interrupteurs S1 (MODE0 à MODE2) changent seulement la taille du micropas, pas le couple : si on les change, refaire le nombre de pas par tour et les Hz.
- Un moteur qui manque de force : regarder la DEL D1 du PCB-01 (protection de surintensité) et la tension d'alimentation sous charge.

## Moteur DC du bras (drive_motor.c) : module L298N, canal A
| Carte (PCB-12, P13) | Module L298N |
|---|---|
| pin 2 (PD12, TIM4 CH1) | IN1 |
| pin 1 (PD13, TIM4 CH2) | IN2 |
| pin 5 (GND) | borne GND, la même que le - de l'alimentation |
| - | cavalier ENA EN PLACE (ENA = 5 V en permanence) |

- Vitesse et sens par PWM sur IN1 ou IN2 (l'autre à 0), 10 kHz. Table du L298 (datasheet ST) avec ENA haut : IN1 = H / IN2 = L dans un sens, IN1 = L / IN2 = H dans l'autre, IN1 = IN2 = frein. DRIVEMOTOR_HORAIRE = PWM sur IN1, DRIVEMOTOR_ANTIHORAIRE = PWM sur IN2.
- Vérin sur OUT1 et OUT2. Alimentation 12 V : + sur la borne 12V, - sur la borne GND. Borne 5V vide, cavalier 5V-EN laissé en place. IN3, IN4, ENB inutilisés. PD14 et PD15 libres.
- P13 (schéma PCB-12 Rev B-02) : pins 1 à 4 reliées directement à PD13 / PD12 / PD15 / PD14, pin 5 = GND, pin 6 = 3,3 V.
- Les DEL de la Discovery sont sur les mêmes broches : LD4 verte = IN1 (PD12), LD3 orange = IN2 (PD13). Elles montrent ce que le STM32 envoie au module, sans rien débrancher.
- Le L298N perd environ 2 V : le vérin reçoit environ 10 V.
- Vérin : course 102 mm, 53 mm/s à vide, 26 mm/s en charge, arrêt interne en bout de course, aucun retour de position (position = vitesse x durée).

## Capteurs d'étage
ClickBoard TCA6416A, 3 capteurs inductifs : `INDUCTIVE_PIN_1` à `3` = 7, 6, 5 pour les étages 1 (bas) à 3, niveau actif 0 (inductive_sensor.h).

## Pas encore fait
- CAN (protocole v1.6 de l'équipe) : à brancher sur les points d'entrée ci-dessus.
- Tester le bras, puis Home / Store / Retrieve sur la carte ; mesurer le temps réel du bras.
