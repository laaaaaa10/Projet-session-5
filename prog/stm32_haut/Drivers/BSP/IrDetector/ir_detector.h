/*
 * ir_detector.h
 *
 *  Created on: 18 nov. 2026
 *      Author: Jonathan Marois
 */

#ifndef BSP_IRDETECTOR_IR_DETECTOR_H_
#define BSP_IRDETECTOR_IR_DETECTOR_H_

#include "stm32f4xx_hal.h"
#include "clickboard_io_mux.h"

typedef struct
{
    ClickBoard_HandleTypeDef *clickboard;

    /* TODO : PWM 38 kHz (timer à activer dans CubeMX) et autres champs */

} IrDetector_HandleTypeDef;

HAL_StatusTypeDef IrDetector_Init(
    IrDetector_HandleTypeDef *dev,
    ClickBoard_HandleTypeDef *clickboard
);

HAL_StatusTypeDef IrDetector_StartEmitter(
    IrDetector_HandleTypeDef *dev
);

HAL_StatusTypeDef IrDetector_StopEmitter(
    IrDetector_HandleTypeDef *dev
);

HAL_StatusTypeDef IrDetector_Read(
    IrDetector_HandleTypeDef *dev,
    uint8_t *detected
);

#endif /* BSP_IRDETECTOR_IR_DETECTOR_H_ */
