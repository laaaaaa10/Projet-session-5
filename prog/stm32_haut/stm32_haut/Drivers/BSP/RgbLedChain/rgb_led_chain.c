/*
 * rgb_led_chain.c
 *
 *  Created on: 18 nov. 2026
 *      Author: Jonathan Marois
 */


#include "rgb_led_chain.h"

HAL_StatusTypeDef RgbLedChain_Init(
    RgbLedChain_HandleTypeDef *dev,
    SPI_HandleTypeDef *hspi,
    uint8_t led_count)
{
    /* TODO */
    return HAL_ERROR;
}

HAL_StatusTypeDef RgbLedChain_SetColor(
    RgbLedChain_HandleTypeDef *dev,
    uint8_t index,
    uint8_t red,
    uint8_t green,
    uint8_t blue,
    uint8_t brightness)
{
    /* TODO */
    return HAL_ERROR;
}

HAL_StatusTypeDef RgbLedChain_Show(
    RgbLedChain_HandleTypeDef *dev)
{
    /* TODO */
    return HAL_ERROR;
}

HAL_StatusTypeDef RgbLedChain_Clear(
    RgbLedChain_HandleTypeDef *dev)
{
    /* TODO */
    return HAL_ERROR;
}
