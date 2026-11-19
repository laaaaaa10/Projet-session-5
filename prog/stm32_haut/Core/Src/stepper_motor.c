/*
 * stepper.c
 *
 *  Created on: 19 nov. 2026
 *      Author: Jonathan Marois
 */


#include "stepper_motor.h"
#include "main.h"

extern TIM_HandleTypeDef htim3;
extern TIM_HandleTypeDef htim12;

/* Moteur de rotation : STEP = PB1 (TIM3 CH4), DIR = PD2 */
Stepper_HandleTypeDef stepper_rotation = { &htim3,  TIM_CHANNEL_4, DIR_ROTATION_GPIO_Port, DIR_ROTATION_Pin };

/* Moteur de hauteur : STEP = PB14 (TIM12 CH1), DIR = PC8 */
Stepper_HandleTypeDef stepper_height   = { &htim12, TIM_CHANNEL_1, DIR_HEIGHT_GPIO_Port,   DIR_HEIGHT_Pin };

HAL_StatusTypeDef Stepper_Rotate(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t steps, uint32_t freq_hz)
{
    if ((dev == NULL) || (steps == 0U) || (freq_hz == 0U))
    {
        return HAL_ERROR;
    }

    /* Période du PWM en ticks de 1 MHz (timers 16 bits) */
    uint32_t periode = (STEPPER_TICK_HZ / freq_hz) - 1U;
    if (periode > 0xFFFFU)
    {
        return HAL_ERROR;
    }

    HAL_GPIO_WritePin(dev->dir_port, dev->dir_pin, (GPIO_PinState)sens);   /* sens de rotation */

    __HAL_TIM_SET_AUTORELOAD(dev->htim, periode);                          /* fréquence de STEP */
    __HAL_TIM_SET_COMPARE(dev->htim, dev->channel, (periode + 1U) / 2U);   /* 50 % */
    __HAL_TIM_SET_COUNTER(dev->htim, 0U);

    if (HAL_TIM_PWM_Start(dev->htim, dev->channel) != HAL_OK)
    {
        return HAL_ERROR;
    }
    HAL_Delay((steps * 1000U) / freq_hz);                                  /* durée = pas / fréquence */

    return HAL_TIM_PWM_Stop(dev->htim, dev->channel);
}
