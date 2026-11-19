/*
 * inductive_sensor.c
 *
 *  Created on: 18 nov. 2026
 *      Author: Jonathan Marois
 */


#include "inductive_sensor.h"

static const uint8_t sensor_pin[INDUCTIVE_SENSOR_COUNT] =
{
    INDUCTIVE_PIN_1,
    INDUCTIVE_PIN_2,
    INDUCTIVE_PIN_3
};

HAL_StatusTypeDef InductiveSensor_Init(
    InductiveSensor_HandleTypeDef *dev,
    ClickBoard_HandleTypeDef *clickboard)
{
    if ((dev == NULL) || (clickboard == NULL))
    {
        return HAL_ERROR;
    }

    dev->clickboard = clickboard;

    for (uint8_t i = 0U; i < INDUCTIVE_SENSOR_COUNT; i++)
    {
        if (ClickBoard_PinMode(clickboard, sensor_pin[i], TCA6416A_INPUT) != HAL_OK)
        {
            return HAL_ERROR;
        }
    }

    return HAL_OK;
}

HAL_StatusTypeDef InductiveSensor_Read(
    InductiveSensor_HandleTypeDef *dev,
    uint8_t sensor,
    uint8_t *active)
{
    if ((dev == NULL) || (dev->clickboard == NULL) || (active == NULL) || (sensor >= INDUCTIVE_SENSOR_COUNT))
    {
        return HAL_ERROR;
    }

    uint8_t level;
    if (ClickBoard_ReadPin(dev->clickboard, sensor_pin[sensor], &level) != HAL_OK)
    {
        return HAL_ERROR;
    }

    *active = (level == INDUCTIVE_ACTIVE_LEVEL) ? 1U : 0U;

    return HAL_OK;
}
