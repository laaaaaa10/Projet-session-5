/*
 * parking_high.h
 *
 *  Created on: 25 nov. 2026
 *      Author: Javier Bolduc
 *
 * Stationnement haut : ascenseur (3 étages) + plateau tournant (7 emplacements). Voir le README.
 */

#ifndef INC_PARKING_HIGH_H_
#define INC_PARKING_HIGH_H_

#include "stm32f4xx_hal.h"

#define PARKING_FLOOR_COUNT         3U

/* Étage 1 = quai, étages 2-3 = stockage. À confirmer avec l'équipe. */
#define PARKING_SLOTS_PER_FLOOR     7U
#define PARKING_SPACE_COUNT         ((PARKING_FLOOR_COUNT - 1U) * PARKING_SLOTS_PER_FLOOR)

/* ClickBoard (I2C) + capteurs d'étage. */
HAL_StatusTypeDef ParkingHigh_Init(I2C_HandleTypeDef *hi2c);

/* Dans while(1). Vide pour l'instant : le CAN s'y branchera. */
void ParkingHigh_Process(void);

/* Points d'entrée pour le CAN. Bloquants (sauf IsBusy). HAL_OK = fait ; sinon refusé ou échec (refaire Home). */
HAL_StatusTypeDef ParkingHigh_Home(void);
HAL_StatusTypeDef ParkingHigh_Store(uint8_t space);         /* case 1 à 14, refusé avant Home */
HAL_StatusTypeDef ParkingHigh_Retrieve(uint8_t space);      /* case 1 à 14, refusé avant Home */
uint8_t           ParkingHigh_IsBusy(void);

#endif /* INC_PARKING_HIGH_H_ */
