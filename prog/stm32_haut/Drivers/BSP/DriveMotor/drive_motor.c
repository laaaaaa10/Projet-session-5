/*
 * drive_motor.c
 *
 *  Created on: 26 nov. 2026
 *      Author: Javier Bolduc
 *
 * PWM sur TIM4 CH1 (PD12 -> IN1) et CH2 (PD13 -> IN2), configuré ici (pas dans CubeMX).
 */

#include "drive_motor.h"

#define DRIVEMOTOR_TIM_CLK_HZ   84000000U
#define DRIVEMOTOR_PWM_HZ       10000U
#define DRIVEMOTOR_PERIOD       ((DRIVEMOTOR_TIM_CLK_HZ / DRIVEMOTOR_PWM_HZ) - 1U)

static TIM_HandleTypeDef htim_dc;
static uint8_t initialised = 0U;

/* Rapport cyclique (%) sur IN1 et IN2. Un seul des deux à la fois ; 0 / 0 = arrêt. */
static void set_pwm(uint32_t in1_percent, uint32_t in2_percent)
{
    __HAL_TIM_SET_COMPARE(&htim_dc, TIM_CHANNEL_1, ((DRIVEMOTOR_PERIOD + 1U) * in1_percent) / 100U);
    __HAL_TIM_SET_COMPARE(&htim_dc, TIM_CHANNEL_2, ((DRIVEMOTOR_PERIOD + 1U) * in2_percent) / 100U);
}

HAL_StatusTypeDef DriveMotor_Init(void)
{
    GPIO_InitTypeDef gpio = {0};
    TIM_OC_InitTypeDef oc = {0};

    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_TIM4_CLK_ENABLE();

    htim_dc.Instance = TIM4;
    htim_dc.Init.Prescaler = 0U;
    htim_dc.Init.CounterMode = TIM_COUNTERMODE_UP;
    htim_dc.Init.Period = DRIVEMOTOR_PERIOD;
    htim_dc.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
    htim_dc.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
    if (HAL_TIM_PWM_Init(&htim_dc) != HAL_OK)
    {
        return HAL_ERROR;
    }

    oc.OCMode = TIM_OCMODE_PWM1;
    oc.Pulse = 0U;
    oc.OCPolarity = TIM_OCPOLARITY_HIGH;
    oc.OCFastMode = TIM_OCFAST_DISABLE;
    if ((HAL_TIM_PWM_ConfigChannel(&htim_dc, &oc, TIM_CHANNEL_1) != HAL_OK) ||
        (HAL_TIM_PWM_ConfigChannel(&htim_dc, &oc, TIM_CHANNEL_2) != HAL_OK) ||
        (HAL_TIM_PWM_Start(&htim_dc, TIM_CHANNEL_1) != HAL_OK) ||
        (HAL_TIM_PWM_Start(&htim_dc, TIM_CHANNEL_2) != HAL_OK))
    {
        return HAL_ERROR;
    }

    gpio.Pin = GPIO_PIN_12 | GPIO_PIN_13;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    gpio.Alternate = GPIO_AF2_TIM4;
    HAL_GPIO_Init(GPIOD, &gpio);

    initialised = 1U;
    return HAL_OK;
}

HAL_StatusTypeDef DriveMotor_Run(DriveMotorSens_t sens, uint8_t duty_percent)
{
    uint32_t duty = (duty_percent > 100U) ? 100U : duty_percent;

    if (initialised == 0U)
    {
        return HAL_ERROR;
    }
    if ((uint32_t)sens != 0U)
    {
        set_pwm(duty, 0U);
    }
    else
    {
        set_pwm(0U, duty);
    }
    return HAL_OK;
}

HAL_StatusTypeDef DriveMotor_Stop(void)
{
    if (initialised == 0U)
    {
        return HAL_ERROR;
    }
    set_pwm(0U, 0U);
    return HAL_OK;
}

HAL_StatusTypeDef DriveMotor_Move(DriveMotorSens_t sens, uint8_t duty_percent, uint32_t duration_ms)
{
    if ((duty_percent == 0U) || (duration_ms == 0U))
    {
        return HAL_ERROR;
    }
    if (DriveMotor_Run(sens, duty_percent) != HAL_OK)
    {
        return HAL_ERROR;
    }
    HAL_Delay(duration_ms);
    return DriveMotor_Stop();
}
