/*
 * parking_high.h
 *
 *  Created on: 25 nov. 2026
 *      Author: Javier Bolduc
 *
 * Logique du stationnement haut : ascenseur (3 étages) + plateau tournant (7 emplacements).
 * Voir le README (intégration, réglages).
 */

#ifndef INC_PARKING_HIGH_H_
#define INC_PARKING_HIGH_H_

#include "stm32f4xx_hal.h"
#include "stepper_motor.h"

/* 1 = ParkingHigh_Process() fait la séquence de TEST. 0 = rien ne bouge tout seul. */
#define PARKING_DEMO_LOOP           1U

/* Sens du plateau (emplacement 1 -> 7). Si le plateau part vers le secteur vide, inverser. */
#define PARKING_FORWARD             STEPPER_HORAIRE
#define PARKING_BACKWARD            ((PARKING_FORWARD == STEPPER_HORAIRE) ? STEPPER_ANTIHORAIRE : STEPPER_HORAIRE)

/* Sens de l'ascenseur. S'il descend quand il devrait monter, inverser. */
#define PARKING_UP                  STEPPER_ANTIHORAIRE
#define PARKING_DOWN                ((PARKING_UP == STEPPER_HORAIRE) ? STEPPER_ANTIHORAIRE : STEPPER_HORAIRE)

#define PARKING_FLOOR_COUNT         3U

/* Initialise le ClickBoard (I2C) et les capteurs d'étage. */
HAL_StatusTypeDef ParkingHigh_Init(I2C_HandleTypeDef *hi2c);

/* Dans while(1). BLOQUANT. */
void ParkingHigh_Process(void);

/* Points d'entrée pour le CAN (à brancher à la fin). HAL_OK = exécuté, HAL_ERROR = refusé ou échec. */
HAL_StatusTypeDef ParkingHigh_Home(void);
HAL_StatusTypeDef ParkingHigh_Store(uint8_t space);         /* case 1 à 14 */
HAL_StatusTypeDef ParkingHigh_Retrieve(uint8_t space);      /* case 1 à 14 */
uint8_t           ParkingHigh_IsBusy(void);

#endif /* INC_PARKING_HIGH_H_ */
