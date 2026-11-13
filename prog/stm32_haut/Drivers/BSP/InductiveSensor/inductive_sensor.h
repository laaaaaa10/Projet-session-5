/*
 * inductive_sensor.h
 *
 *  Created on: 18 nov. 2026
 *      Author: Jonathan Marois
 */

#ifndef BSP_INDUCTIVESENSOR_INDUCTIVE_SENSOR_H_
#define BSP_INDUCTIVESENSOR_INDUCTIVE_SENSOR_H_

#include "stm32f4xx_hal.h"
#include "clickboard_io_mux.h"

typedef struct
{
    ClickBoard_HandleTypeDef *clickboard;

    /* TODO : autres champs au besoin */

} InductiveSensor_HandleTypeDef;

HAL_StatusTypeDef InductiveSensor_Init(
    InductiveSensor_HandleTypeDef *dev,
    ClickBoard_HandleTypeDef *clickboard
);

HAL_StatusTypeDef InductiveSensor_Read(
    InductiveSensor_HandleTypeDef *dev,
    uint8_t sensor,
    uint8_t *active
);

#endif /* BSP_INDUCTIVESENSOR_INDUCTIVE_SENSOR_H_ */
