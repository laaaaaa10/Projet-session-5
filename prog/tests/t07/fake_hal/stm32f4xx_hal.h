/* Faux HAL minimal pour tester rgb_led_chain.c sur PC (pas de matériel). */
#ifndef FAKE_STM32F4XX_HAL_H
#define FAKE_STM32F4XX_HAL_H

#include <stdint.h>
#include <stddef.h>

typedef enum { HAL_OK = 0, HAL_ERROR = 1, HAL_BUSY = 2, HAL_TIMEOUT = 3 } HAL_StatusTypeDef;
typedef enum { HAL_SPI_STATE_RESET = 0, HAL_SPI_STATE_READY = 1, HAL_SPI_STATE_BUSY_TX = 3 } HAL_SPI_StateTypeDef;

typedef struct { int dummy; } DMA_HandleTypeDef;
typedef struct { int dummy; } CAN_HandleTypeDef;

typedef struct
{
    DMA_HandleTypeDef   *hdmatx;
    HAL_SPI_StateTypeDef State;
    /* Espion : dernière trame envoyée */
    const uint8_t *last_data;
    uint16_t       last_size;
    int            dma_calls;
    int            blocking_calls;
} SPI_HandleTypeDef;

HAL_SPI_StateTypeDef HAL_SPI_GetState(SPI_HandleTypeDef *hspi);
HAL_StatusTypeDef HAL_SPI_Transmit_DMA(SPI_HandleTypeDef *hspi, uint8_t *pData, uint16_t Size);
HAL_StatusTypeDef HAL_SPI_Transmit(SPI_HandleTypeDef *hspi, uint8_t *pData, uint16_t Size, uint32_t Timeout);

#endif
