/*
 * drive_motor.c
 *
 * Voir drive_motor.h pour le branchement.
 * Le timer TIM4 est configuré ici (pas dans CubeMX) : PD12 = TIM4 CH1, 84 MHz / 4200 = 20 kHz.
 */

#include "drive_motor.h"

#define DRIVEMOTOR_TIM_CLK_HZ   84000000U                                   /* TIM4 sur APB1, comme TIM3 et TIM12 */
#define DRIVEMOTOR_PWM_HZ       20000U
#define DRIVEMOTOR_PERIOD       ((DRIVEMOTOR_TIM_CLK_HZ / DRIVEMOTOR_PWM_HZ) - 1U)
#define DRIVEMOTOR_REVERSE_MS   20U                                         /* pause à l'arrêt avant d'inverser le sens */

#define DRIVEMOTOR_EN_PORT      GPIOD
#define DRIVEMOTOR_EN_PIN       GPIO_PIN_12                                 /* Motor_ON : PWM */
#define DRIVEMOTOR_DIR_PORT     GPIOD
#define DRIVEMOTOR_DIR_PIN      GPIO_PIN_13                                 /* DIR */

static TIM_HandleTypeDef htim_dc;
static uint8_t initialised = 0U;
static uint8_t running = 0U;
static DriveMotorSens_t current_sens = DRIVEMOTOR_RENTRER;

static void set_duty(uint8_t percent)
{
    if (percent > 100U)
    {
        percent = 100U;
    }
    __HAL_TIM_SET_COMPARE(&htim_dc, TIM_CHANNEL_1, ((DRIVEMOTOR_PERIOD + 1U) * percent) / 100U);
}

HAL_StatusTypeDef DriveMotor_Init(void)
{
    GPIO_InitTypeDef gpio = {0};
    TIM_OC_InitTypeDef oc = {0};

    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_TIM4_CLK_ENABLE();

    /* DIR : sortie, niveau bas */
    HAL_GPIO_WritePin(DRIVEMOTOR_DIR_PORT, DRIVEMOTOR_DIR_PIN, GPIO_PIN_RESET);
    gpio.Pin = DRIVEMOTOR_DIR_PIN;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(DRIVEMOTOR_DIR_PORT, &gpio);

    /* PWM sur TIM4 CH1, rapport cyclique 0 % : Motor_ON reste à 0 */
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
    if (HAL_TIM_PWM_ConfigChannel(&htim_dc, &oc, TIM_CHANNEL_1) != HAL_OK)
    {
        return HAL_ERROR;
    }
    if (HAL_TIM_PWM_Start(&htim_dc, TIM_CHANNEL_1) != HAL_OK)
    {
        return HAL_ERROR;
    }

    /* PD12 passe du GPIO (LED LD4 par défaut) à la sortie du timer, seulement quand tout est prêt */
    gpio.Pin = DRIVEMOTOR_EN_PIN;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    gpio.Alternate = GPIO_AF2_TIM4;
    HAL_GPIO_Init(DRIVEMOTOR_EN_PORT, &gpio);

    running = 0U;
    initialised = 1U;
    return HAL_OK;
}

HAL_StatusTypeDef DriveMotor_Run(DriveMotorSens_t sens, uint8_t duty_percent)
{
    if (initialised == 0U)
    {
        return HAL_ERROR;
    }
    if (duty_percent == 0U)
    {
        return DriveMotor_Stop();
    }

    if ((running != 0U) && (sens != current_sens))
    {
        set_duty(0U);                          /* arrêt avant d'inverser le sens */
        HAL_Delay(DRIVEMOTOR_REVERSE_MS);
    }

    HAL_GPIO_WritePin(DRIVEMOTOR_DIR_PORT, DRIVEMOTOR_DIR_PIN, (GPIO_PinState)sens);
    current_sens = sens;
    set_duty(duty_percent);
    running = 1U;
    return HAL_OK;
}

HAL_StatusTypeDef DriveMotor_Stop(void)
{
    if (initialised == 0U)
    {
        return HAL_ERROR;
    }
    set_duty(0U);
    running = 0U;
    return HAL_OK;
}
