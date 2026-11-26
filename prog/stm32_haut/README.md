# STM32 HAUT : notes

Rien de ce qui est décrit ici n'a été testé sur la carte.

## Intégration (main.c)
```c
DriveMotor_Init();
ParkingHigh_Init(&hi2c1);   // une fois, après les MX_..._Init
ParkingHigh_Process();      // dans while(1)
```

## Plateau et ascenseur (parking_high.c)
- Les valeurs qui changent (pas, Hz, pauses, timeout) sont écrites directement dans les appels, pas dans le .h.
- `Stepper_Rotate(&stepper_rotation, sens, pas, Hz)` : bloquant, avec rampe d'accélération. 2000 pas = 1 tour (mesuré), donc 1 emplacement = 250 pas = 45 degrés. pas = degrés x 2000 / 360.
- `go_to_floor(étage, sens)` : monte ou descend jusqu'au capteur de l'étage 1 à 3 (250 Hz, timeout 120 s). Retourne HAL_OK, HAL_TIMEOUT ou HAL_ERROR.
- `PARKING_DEMO_LOOP` (parking_high.h) : 1 = `ParkingHigh_Process()` fait un aller-retour de 45 degrés du plateau (test), 0 = rien ne bouge tout seul.
- Sens à confirmer sur la carte : `PARKING_FORWARD`, `PARKING_UP` (les sens opposés s'en déduisent), `DRIVEMOTOR_SORTIR` / `DRIVEMOTOR_RENTRER`.

## Moteurs pas-à-pas (stepper_motor.c)
- Jeux de broches (STEP / DIR), choisis en haut du .c avec `STEPPER_ROTATION_PINS` (2) et `STEPPER_HEIGHT_PINS` (1) :

| Jeu | STEP | DIR | Note |
|---|---|---|---|
| 0 | PB14 | PC8 | en panne, ne pas utiliser |
| 1 | PB0 (TIM3 CH3) | PC4 | P11 pin 4 / pin 1 |
| 2 | PA2 (TIM5 CH3) | PA3 | P11 pin 2 / pin 3 |

- P11 (PMOD UART) : pin 1 = PC4, pin 2 = PA2, pin 3 = PA3, pin 4 = PB0. Les jeux 1 et 2 sont configurés par le .c (rien à faire dans CubeMX). Broches mortes connues : PB1, PD2, PB14, PC8.
- Rampe : `STEPPER_START_HZ` (60) et `STEPPER_RAMP_MS` (800), en haut du .c. Si un moteur cale : baisser la fréquence demandée ou `STEPPER_START_HZ`, ou allonger `STEPPER_RAMP_MS`.
- Drive PCB-01 : pas de potentiomètre de courant (Vref fixe, le courant est fixé par le moteur, environ 0,35 A). Les interrupteurs S1 (MODE0 à MODE2) changent seulement la taille du micropas, pas le couple : si on les change, refaire le nombre de pas par tour.
- Un moteur qui manque de force : regarder la DEL D1 du PCB-01 (protection de surintensité) et la tension d'alimentation sous charge.

## Moteur DC du bras (drive_motor.c) : module L298N, canal A
| Carte (PCB-12, P13) | Module L298N |
|---|---|
| pin 2 (PD12, PWM) | ENA (enlever le cavalier ENA) |
| pin 1 (PD13) | IN1 |
| pin 3 (PD15) | IN2 |
| GND | borne GND, la même que le - de l'alimentation |

- Vérin sur OUT1 et OUT2. Alimentation 12 V : + sur la borne 12V, - sur la borne GND. Borne 5V vide, cavalier 5V-EN laissé en place. IN3, IN4, ENB inutilisés.
- ENA, IN1, IN2 sont sur la rangée de petites broches du module, pas sur les bornes à vis.
- P13 pin 5 est probablement un GND : à vérifier au multimètre. PD15 s'appelle SenseA sur le schéma, elle sert ici de sortie IN2. PD14 reste libre.
- Le L298N perd environ 2 V : le vérin reçoit environ 10 V. PWM de 10 kHz.
- Vérin : course 102 mm, 53 mm/s à vide, 26 mm/s en charge, arrêt interne en bout de course, aucun retour de position (position = vitesse x durée).

## Capteurs d'étage
ClickBoard TCA6416A, 3 capteurs inductifs : `INDUCTIVE_PIN_1` à `3` = 7, 6, 5 pour les étages 1 (bas) à 3, niveau actif 0 (inductive_sensor.h).

## Pas encore fait
- CAN : `ParkingHigh_Home / Store / Retrieve / IsBusy` sont vides (TODO dans parking_high.c).
- Correspondance case 1 à 14 -> étage + emplacement.
