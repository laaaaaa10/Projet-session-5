/*
 * rgb_led_chain.h
 *
 *  Created on: 18 nov. 2026
 *      Author: Jonathan Marois
 */

#ifndef BSP_RGBLEDCHAIN_RGB_LED_CHAIN_H_
#define BSP_RGBLEDCHAIN_RGB_LED_CHAIN_H_

#include "stm32f4xx_hal.h"

typedef struct
{
    SPI_HandleTypeDef *hspi;
    uint8_t led_count;

    /* TODO : autres champs au besoin */

} RgbLedChain_HandleTypeDef;

HAL_StatusTypeDef RgbLedChain_Init(
    RgbLedChain_HandleTypeDef *dev,
    SPI_HandleTypeDef *hspi,
    uint8_t led_count
);

HAL_StatusTypeDef RgbLedChain_SetColor(
    RgbLedChain_HandleTypeDef *dev,
    uint8_t index,
    uint8_t red,
    uint8_t green,
    uint8_t blue,
    uint8_t brightness
);

HAL_StatusTypeDef RgbLedChain_Show(
    RgbLedChain_HandleTypeDef *dev
);

HAL_StatusTypeDef RgbLedChain_Clear(
    RgbLedChain_HandleTypeDef *dev
);

#endif /* BSP_RGBLEDCHAIN_RGB_LED_CHAIN_H_ */
