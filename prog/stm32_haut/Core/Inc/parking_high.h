/*
 * parking_high.h
 *
 *  Created on: 25 nov. 2026
 *      Author: Layten
 *
 * Logique du stationnement haut : ascenseur (3 étages, capteurs inductifs) + plateau tournant
 * (7 emplacements sur 8 secteurs de 45 degrés, le 8e secteur est vide).
 *
 * Les mouvements sont des appels bloquants (l'accélération est gérée dans le driver stepper_motor.c) :
 *     Stepper_Rotate(&stepper_rotation, sens, pas, Hz);   tourne le plateau
 *     go_to_floor(2U, PARKING_UP);                        monte / descend jusqu'au capteur de l'étage 2
 *
 * Intégration dans main.c :
 *     ParkingHigh_Init(&hi2c1);     une fois, après les MX_..._Init
 *     ParkingHigh_Process();        dans while(1)
 */

#ifndef INC_PARKING_HIGH_H_
#define INC_PARKING_HIGH_H_

#include "stm32f4xx_hal.h"
#include "stepper_motor.h"

/* 1 = ParkingHigh_Process() fait une séquence de TEST (un appel = un cycle, voir parking_high.c).
 * 0 = rien ne bouge tout seul. */
#define PARKING_DEMO_LOOP           1U

/* --- Plateau tournant --- */
#define PARKING_ROTATION_HZ         200U                /* vitesse (pas/s), plus bas = plus de force */
#define PARKING_SPACE_STEPS         250U                /* pas pour avancer d'un emplacement (2000 pas = 1 tour, 8 secteurs) */
#define PARKING_FORWARD             STEPPER_HORAIRE     /* emplacement 1 -> 7. Si le plateau part vers le secteur vide, inverser. */
#define PARKING_BACKWARD            ((PARKING_FORWARD == STEPPER_HORAIRE) ? STEPPER_ANTIHORAIRE : STEPPER_HORAIRE)

/* --- Hauteur --- */
#define PARKING_HEIGHT_HZ           250U                /* vitesse (pas/s) */
#define PARKING_UP                  STEPPER_ANTIHORAIRE /* sens "monter". Si l'ascenseur descend quand il devrait monter, inverser. */
#define PARKING_DOWN                ((PARKING_UP == STEPPER_HORAIRE) ? STEPPER_ANTIHORAIRE : STEPPER_HORAIRE)
#define PARKING_HEIGHT_TIMEOUT_MS   120000U             /* étage non atteint après ce délai : le moteur s'arrête */
#define PARKING_FLOOR_COUNT         3U                  /* capteurs 1 (bas) à 3 (haut) */

#define PARKING_DWELL_MS            3000U               /* pause à chaque étage (séquence de test seulement) */

/* Initialise le ClickBoard (I2C) et les capteurs d'étage. Ne bouge aucun moteur. */
HAL_StatusTypeDef ParkingHigh_Init(I2C_HandleTypeDef *hi2c);

/* À appeler dans la boucle principale. BLOQUANT : avec PARKING_DEMO_LOOP = 1, un appel = un cycle de test. */
void ParkingHigh_Process(void);

/* Points d'entrée pour le CAN (ajouté à la fin). La logique est à écrire dans parking_high.c, voir les TODO.
 * Retour : HAL_OK = exécuté, HAL_ERROR = refusé ou échec. */
HAL_StatusTypeDef ParkingHigh_Home(void);                   /* initialisation des axes (fins de course) */
HAL_StatusTypeDef ParkingHigh_Store(uint8_t space);         /* ranger un véhicule dans la case 1 à 14 */
HAL_StatusTypeDef ParkingHigh_Retrieve(uint8_t space);      /* récupérer le véhicule de la case 1 à 14 */
uint8_t           ParkingHigh_IsBusy(void);                 /* 1 pendant un déplacement, 0 sinon */

#endif /* INC_PARKING_HIGH_H_ */