/*
 * rgb_led_chain.h
 *
 *  Created on: 18 nov. 2026
 *      Author: Jonathan Marois (squelette)
 *  Complété le 24 nov. 2026 par William MacDonald (T07)
 *
 * Pilote d'une chaîne de DEL RGB adressables BL-HBGR32L-3-TRB-8
 * (protocole de type APA102 : horloge + données, lues sur le front montant).
 *
 * Trame envoyée sur le SPI (MSB d'abord, SPI mode 0) :
 *   - début : 4 octets à 0x00
 *   - une trame de 4 octets par DEL, dans l'ordre de la chaîne (indice 0 = 1re DEL) :
 *       [0b111 + luminosité globale sur 5 bits] [bleu] [vert] [rouge]
 *   - fin : 4 octets à 0xFF (assez de fronts d'horloge pour pousser
 *     les données jusqu'à la dernière DEL, jusqu'à 64 DEL)
 *
 * Utilisation :
 *   1. RgbLedChain_Init()      : prépare l'image (toutes les DEL éteintes), n'envoie rien.
 *   2. RgbLedChain_SetColor()  : modifie l'image en mémoire seulement.
 *   3. RgbLedChain_Show()      : envoie l'image. Par DMA si le SPI a un DMA TX
 *                                (non bloquant), sinon en mode bloquant (< 1 ms).
 *
 * Le handle doit être une variable globale ou statique : le DMA lit tx_frame
 * après le retour de RgbLedChain_Show().
 */

#ifndef BSP_RGBLEDCHAIN_RGB_LED_CHAIN_H_
#define BSP_RGBLEDCHAIN_RGB_LED_CHAIN_H_

#include "stm32f4xx_hal.h"

/* Nombre maximal de DEL par chaîne (PCB-03 : 15 ; PCB-08 : 8). */
#define RGB_LED_CHAIN_MAX_LEDS          32u

/* Luminosité globale de la DEL, sur 5 bits (0 à 31). */
#define RGB_LED_CHAIN_BRIGHTNESS_MAX    31u

/* Taille des parties de la trame, en octets. */
#define RGB_LED_CHAIN_START_BYTES       4u
#define RGB_LED_CHAIN_BYTES_PER_LED     4u
#define RGB_LED_CHAIN_END_BYTES         4u
#define RGB_LED_CHAIN_FRAME_MAX_BYTES   (RGB_LED_CHAIN_START_BYTES \
                                         + (RGB_LED_CHAIN_BYTES_PER_LED * RGB_LED_CHAIN_MAX_LEDS) \
                                         + RGB_LED_CHAIN_END_BYTES)

/* Délai maximal d'un envoi bloquant (repli sans DMA). */
#define RGB_LED_CHAIN_TIMEOUT_MS        10u

typedef struct
{
    SPI_HandleTypeDef *hspi;        /* SPI relié au PCB-11 (horloge et données des DEL) */
    uint8_t  led_count;             /* nombre de DEL dans la chaîne */
    uint16_t frame_size;            /* taille de la trame complète, en octets */
    uint8_t  frame[RGB_LED_CHAIN_FRAME_MAX_BYTES];     /* image modifiée par SetColor */
    uint8_t  tx_frame[RGB_LED_CHAIN_FRAME_MAX_BYTES];  /* copie lue par le DMA pendant l'envoi */

} RgbLedChain_HandleTypeDef;

/* Prépare la chaîne : toutes les DEL éteintes dans l'image. N'envoie rien.
 * HAL_ERROR si un pointeur est nul ou si led_count vaut 0 ou dépasse RGB_LED_CHAIN_MAX_LEDS. */
HAL_StatusTypeDef RgbLedChain_Init(
    RgbLedChain_HandleTypeDef *dev,
    SPI_HandleTypeDef *hspi,
    uint8_t led_count
);

/* Change la couleur d'une DEL dans l'image (sans l'envoyer).
 * index : 0 à led_count - 1 ; red, green, blue : 0 à 255 ; brightness : 0 à 31.
 * HAL_ERROR si l'indice ou la luminosité est hors plage : l'image n'est pas modifiée. */
HAL_StatusTypeDef RgbLedChain_SetColor(
    RgbLedChain_HandleTypeDef *dev,
    uint8_t index,
    uint8_t red,
    uint8_t green,
    uint8_t blue,
    uint8_t brightness
);

/* Envoie l'image actuelle à la chaîne.
 * HAL_BUSY si l'envoi précédent n'est pas terminé (rappeler plus tard). */
HAL_StatusTypeDef RgbLedChain_Show(
    RgbLedChain_HandleTypeDef *dev
);

/* Éteint toutes les DEL dans l'image (sans l'envoyer : appeler RgbLedChain_Show). */
HAL_StatusTypeDef RgbLedChain_Clear(
    RgbLedChain_HandleTypeDef *dev
);

#endif /* BSP_RGBLEDCHAIN_RGB_LED_CHAIN_H_ */
