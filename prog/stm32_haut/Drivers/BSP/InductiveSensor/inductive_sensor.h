/*
 * inductive_sensor.h
 *
 *  Created on: 18 nov. 2026
 *      Author: Javier Bolduc
 */

#ifndef BSP_INDUCTIVESENSOR_INDUCTIVE_SENSOR_H_
#define BSP_INDUCTIVESENSOR_INDUCTIVE_SENSOR_H_

#include "stm32f4xx_hal.h"
#include "clickboard_io_mux.h"

/* Trois capteurs d'étage : Omron E2B-M12KS04-WP-C2 (NPN collecteur ouvert, normalement fermé) */
#define INDUCTIVE_SENSOR_COUNT   3U

/* Pins du connecteur J1 du ClickBoard (P0.x) où sont branchées les sorties des capteurs 1, 2 et 3 */
#define INDUCTIVE_PIN_1          7U
#define INDUCTIVE_PIN_2          6U
#define INDUCTIVE_PIN_3          5U

/* Niveau lu quand la cible métallique est détectée.
 * Mesuré sur le banc : cible présente = 0, pas de cible = 1. */
#define INDUCTIVE_ACTIVE_LEVEL   0U

typedef struct
{
    ClickBoard_HandleTypeDef *clickboard;

} InductiveSensor_HandleTypeDef;

/* Le ClickBoard (TCA6416A) doit déjà être initialisé. Configure les 3 entrées. */
HAL_StatusTypeDef InductiveSensor_Init(
    InductiveSensor_HandleTypeDef *dev,
    ClickBoard_HandleTypeDef *clickboard
);

/* sensor : 0 à 2. active = 1 si la cible est détectée, 0 sinon. */
HAL_StatusTypeDef InductiveSensor_Read(
    InductiveSensor_HandleTypeDef *dev,
    uint8_t sensor,
    uint8_t *active
);

#endif /* BSP_INDUCTIVESENSOR_INDUCTIVE_SENSOR_H_ */
