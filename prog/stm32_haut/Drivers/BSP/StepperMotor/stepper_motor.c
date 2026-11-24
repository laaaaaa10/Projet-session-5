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

/* Moteur de rotation : STEP = PB0 (TIM3 CH3), DIR = PC4  (PMOD UART P11 : IO2 = pin 4, IO1 = pin 1)
 * Remplace PB1 / PD2 (MikroBus 1) qui ne répondaient plus. Configuré au premier appel de Stepper_Rotate. */
#define ROTATION_STEP_PORT   GPIOB
#define ROTATION_STEP_PIN    GPIO_PIN_0
#define ROTATION_DIR_PORT    GPIOC
#define ROTATION_DIR_PIN     GPIO_PIN_4
Stepper_HandleTypeDef stepper_rotation = { &htim3,  TIM_CHANNEL_3, ROTATION_DIR_PORT, ROTATION_DIR_PIN };

/* Moteur de hauteur : STEP = PB14 (TIM12 CH1), DIR = PC8 */
Stepper_HandleTypeDef stepper_height   = { &htim12, TIM_CHANNEL_1, DIR_HEIGHT_GPIO_Port,   DIR_HEIGHT_Pin };

static uint8_t rotation_ready = 0U;

/* Configure DIR (PC4) et STEP (PB0 = TIM3 CH3) du moteur de rotation. TIM3 est déjà initialisé par CubeMX. */
static HAL_StatusTypeDef rotation_init(void)
{
    GPIO_InitTypeDef gpio = {0};
    TIM_OC_InitTypeDef oc = {0};

    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();

    HAL_GPIO_WritePin(ROTATION_DIR_PORT, ROTATION_DIR_PIN, GPIO_PIN_RESET);
    gpio.Pin = ROTATION_DIR_PIN;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(ROTATION_DIR_PORT, &gpio);

    oc.OCMode = TIM_OCMODE_PWM1;
    oc.Pulse = 0U;
    oc.OCPolarity = TIM_OCPOLARITY_HIGH;
    oc.OCFastMode = TIM_OCFAST_DISABLE;
    if (HAL_TIM_PWM_ConfigChannel(&htim3, &oc, TIM_CHANNEL_3) != HAL_OK)
    {
        return HAL_ERROR;
    }

    gpio.Pin = ROTATION_STEP_PIN;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    gpio.Alternate = GPIO_AF2_TIM3;
    HAL_GPIO_Init(ROTATION_STEP_PORT, &gpio);

    rotation_ready = 1U;
    return HAL_OK;
}

HAL_StatusTypeDef Stepper_Rotate(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t steps, uint32_t freq_hz)
{
    if ((dev == NULL) || (steps == 0U) || (freq_hz == 0U))
    {
        return HAL_ERROR;
    }

    if ((dev == &stepper_rotation) && (rotation_ready == 0U))
    {
        if (rotation_init() != HAL_OK)
        {
            return HAL_ERROR;
        }
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
