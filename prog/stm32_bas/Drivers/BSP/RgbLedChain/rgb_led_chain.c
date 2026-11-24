/*
 * rgb_led_chain.c
 *
 *  Created on: 18 nov. 2026
 *      Author: Jonathan Marois (squelette)
 *  Complété le 24 nov. 2026 par William MacDonald (T07)
 *
 * Voir rgb_led_chain.h pour le format de la trame.
 */

#include "rgb_led_chain.h"
#include <string.h>

/* Premier octet d'une trame de DEL : 3 bits à 1, puis la luminosité sur 5 bits. */
#define LED_HEADER_BITS   0xE0u

/* Adresse des 4 octets de la DEL « index » dans une trame. */
static uint8_t *led_bytes(uint8_t *frame, uint8_t index)
{
    return &frame[RGB_LED_CHAIN_START_BYTES + (RGB_LED_CHAIN_BYTES_PER_LED * (uint16_t)index)];
}

static void write_led(uint8_t *frame, uint8_t index,
                      uint8_t red, uint8_t green, uint8_t blue, uint8_t brightness)
{
    uint8_t *p = led_bytes(frame, index);
    p[0] = (uint8_t)(LED_HEADER_BITS | brightness);
    p[1] = blue;
    p[2] = green;
    p[3] = red;
}

HAL_StatusTypeDef RgbLedChain_Init(
    RgbLedChain_HandleTypeDef *dev,
    SPI_HandleTypeDef *hspi,
    uint8_t led_count)
{
    if ((dev == NULL) || (hspi == NULL) ||
        (led_count == 0u) || (led_count > RGB_LED_CHAIN_MAX_LEDS))
    {
        return HAL_ERROR;
    }

    dev->hspi       = hspi;
    dev->led_count  = led_count;
    dev->frame_size = (uint16_t)(RGB_LED_CHAIN_START_BYTES
                                 + (RGB_LED_CHAIN_BYTES_PER_LED * (uint16_t)led_count)
                                 + RGB_LED_CHAIN_END_BYTES);

    /* Début de trame : 32 bits à 0 */
    memset(dev->frame, 0x00, RGB_LED_CHAIN_START_BYTES);

    /* Toutes les DEL éteintes */
    for (uint8_t i = 0u; i < led_count; i++)
    {
        write_led(dev->frame, i, 0u, 0u, 0u, 0u);
    }

    /* Fin de trame : 32 bits à 1, juste après la dernière DEL */
    memset(&dev->frame[dev->frame_size - RGB_LED_CHAIN_END_BYTES], 0xFF, RGB_LED_CHAIN_END_BYTES);

    memcpy(dev->tx_frame, dev->frame, dev->frame_size);
    return HAL_OK;
}

HAL_StatusTypeDef RgbLedChain_SetColor(
    RgbLedChain_HandleTypeDef *dev,
    uint8_t index,
    uint8_t red,
    uint8_t green,
    uint8_t blue,
    uint8_t brightness)
{
    if ((dev == NULL) || (dev->hspi == NULL) ||
        (index >= dev->led_count) || (brightness > RGB_LED_CHAIN_BRIGHTNESS_MAX))
    {
        return HAL_ERROR;
    }

    write_led(dev->frame, index, red, green, blue, brightness);
    return HAL_OK;
}

HAL_StatusTypeDef RgbLedChain_Show(
    RgbLedChain_HandleTypeDef *dev)
{
    if ((dev == NULL) || (dev->hspi == NULL))
    {
        return HAL_ERROR;
    }

    /* Envoi précédent encore en cours (DMA) : on ne touche pas à tx_frame */
    if (HAL_SPI_GetState(dev->hspi) != HAL_SPI_STATE_READY)
    {
        return HAL_BUSY;
    }

    /* Copie de l'image : SetColor peut la modifier pendant que le DMA lit tx_frame */
    memcpy(dev->tx_frame, dev->frame, dev->frame_size);

    if (dev->hspi->hdmatx != NULL)
    {
        return HAL_SPI_Transmit_DMA(dev->hspi, dev->tx_frame, dev->frame_size);
    }

    /* Repli sans DMA : envoi bloquant (68 octets à 1,3 MHz ≈ 0,4 ms) */
    return HAL_SPI_Transmit(dev->hspi, dev->tx_frame, dev->frame_size, RGB_LED_CHAIN_TIMEOUT_MS);
}

HAL_StatusTypeDef RgbLedChain_Clear(
    RgbLedChain_HandleTypeDef *dev)
{
    if ((dev == NULL) || (dev->hspi == NULL))
    {
        return HAL_ERROR;
    }

    for (uint8_t i = 0u; i < dev->led_count; i++)
    {
        write_led(dev->frame, i, 0u, 0u, 0u, 0u);
    }
    return HAL_OK;
}
