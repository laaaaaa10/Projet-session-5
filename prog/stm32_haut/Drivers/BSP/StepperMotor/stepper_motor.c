/*
 * stepper.c
 *
 *  Created on: 19 nov. 2026
 *      Author: Layten
 */


#include "stepper_motor.h"
#include "main.h"

extern TIM_HandleTypeDef htim3;
extern TIM_HandleTypeDef htim12;

/* ======================= CHOIX DES BROCHES DE CHAQUE MOTEUR =======================
 * Trois jeux de broches (STEP = signal d'impulsions, DIR = sens). Choisir un jeu par moteur plus bas.
 *
 *   JEU 0 : STEP = PB14 (TIM12 CH1), DIR = PC8   (P12 : IO1 / IO2)      <- considéré en panne, ne pas utiliser
 *   JEU 1 : STEP = PB0  (TIM3 CH3),  DIR = PC4   (P11 : pin 4 / pin 1)
 *   JEU 2 : STEP = PA2  (TIM5 CH3),  DIR = PA3   (P11 : pin 2 / pin 3)
 *
 * P11 (PMOD UART, schéma Rev.B) : pin 1 = PC4, pin 2 = PA2, pin 3 = PA3, pin 4 = PB0.
 * Les jeux 1 et 2 sont configurés par ce fichier au premier mouvement (rien à faire dans CubeMX).
 * Changer de jeu = changer un chiffre ci-dessous (et déplacer les fils du driver sur les broches du jeu). */
#define STEPPER_ROTATION_PINS   2
#define STEPPER_HEIGHT_PINS     1

#if (STEPPER_ROTATION_PINS == STEPPER_HEIGHT_PINS)
#error "Les deux moteurs ne peuvent pas utiliser le meme jeu de broches"
#endif

#define SET1_STEP_PORT   GPIOB
#define SET1_STEP_PIN    GPIO_PIN_0
#define SET1_DIR_PORT    GPIOC
#define SET1_DIR_PIN     GPIO_PIN_4

#define SET2_STEP_PORT   GPIOA
#define SET2_STEP_PIN    GPIO_PIN_2
#define SET2_DIR_PORT    GPIOA
#define SET2_DIR_PIN     GPIO_PIN_3

/* TIM5 (jeu 2) n'est pas dans CubeMX : initialisé ici, même horloge de 1 MHz que TIM3/TIM12 (84 MHz / 84). */
static TIM_HandleTypeDef htim_set2;

#define HANDLE_INIT_0   { .htim = &htim12,     .channel = TIM_CHANNEL_1, .dir_port = DIR_HEIGHT_GPIO_Port, .dir_pin = DIR_HEIGHT_Pin, .set = 0U }
#define HANDLE_INIT_1   { .htim = &htim3,      .channel = TIM_CHANNEL_3, .dir_port = SET1_DIR_PORT,        .dir_pin = SET1_DIR_PIN,  .set = 1U }
#define HANDLE_INIT_2   { .htim = &htim_set2,  .channel = TIM_CHANNEL_3, .dir_port = SET2_DIR_PORT,        .dir_pin = SET2_DIR_PIN,  .set = 2U }
#define HANDLE_INIT(n)  HANDLE_INIT_X(n)
#define HANDLE_INIT_X(n) HANDLE_INIT_##n

Stepper_HandleTypeDef stepper_rotation = HANDLE_INIT(STEPPER_ROTATION_PINS);
Stepper_HandleTypeDef stepper_height   = HANDLE_INIT(STEPPER_HEIGHT_PINS);

static uint8_t set_ready[3] = { 1U, 0U, 0U };       /* le jeu 0 est déjà configuré par CubeMX */

/* Configure DIR + STEP d'un jeu (jeux 1 et 2). Le timer du jeu 1 (TIM3) vient déjà de CubeMX. */
static HAL_StatusTypeDef set_init(uint8_t set)
{
    GPIO_InitTypeDef gpio = {0};
    TIM_OC_InitTypeDef oc = {0};
    TIM_HandleTypeDef *htim;
    GPIO_TypeDef *step_port;
    uint16_t step_pin;
    uint32_t af;
    GPIO_TypeDef *dir_port;
    uint16_t dir_pin;

    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();

    if (set == 1U)
    {
        htim = &htim3;
        step_port = SET1_STEP_PORT;  step_pin = SET1_STEP_PIN;  af = GPIO_AF2_TIM3;
        dir_port = SET1_DIR_PORT;    dir_pin = SET1_DIR_PIN;
    }
    else if (set == 2U)
    {
        htim = &htim_set2;
        step_port = SET2_STEP_PORT;  step_pin = SET2_STEP_PIN;  af = GPIO_AF2_TIM5;
        dir_port = SET2_DIR_PORT;    dir_pin = SET2_DIR_PIN;

        __HAL_RCC_TIM5_CLK_ENABLE();
        htim->Instance = TIM5;
        htim->Init.Prescaler = 83U;
        htim->Init.CounterMode = TIM_COUNTERMODE_UP;
        htim->Init.Period = 3570U;
        htim->Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
        htim->Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
        if (HAL_TIM_PWM_Init(htim) != HAL_OK)
        {
            return HAL_ERROR;
        }
    }
    else
    {
        return HAL_ERROR;
    }

    HAL_GPIO_WritePin(dir_port, dir_pin, GPIO_PIN_RESET);
    gpio.Pin = dir_pin;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(dir_port, &gpio);

    oc.OCMode = TIM_OCMODE_PWM1;
    oc.Pulse = 0U;
    oc.OCPolarity = TIM_OCPOLARITY_HIGH;
    oc.OCFastMode = TIM_OCFAST_DISABLE;
    if (HAL_TIM_PWM_ConfigChannel(htim, &oc, TIM_CHANNEL_3) != HAL_OK)
    {
        return HAL_ERROR;
    }

    gpio.Pin = step_pin;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    gpio.Alternate = af;
    HAL_GPIO_Init(step_port, &gpio);

    set_ready[set] = 1U;
    return HAL_OK;
}

/* Écrit DIR, la fréquence de STEP (ARR, rapport cyclique 50 %) et lance le PWM. Rien d'autre. */
static HAL_StatusTypeDef start_at(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t freq_hz)
{
    if ((dev == NULL) || (freq_hz == 0U))
    {
        return HAL_ERROR;
    }

    if ((dev->set > 2U) || ((set_ready[dev->set] == 0U) && (set_init(dev->set) != HAL_OK)))
    {
        return HAL_ERROR;                                                  /* jeu de broches invalide ou init échouée */
    }

    /* Période du PWM en ticks de 1 MHz (max 16 bits, même pour TIM5 qui est en 32 bits) */
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

    dev->running = 1U;
    dev->ramping = 0U;
    dev->move_active = 0U;
    dev->f_now = freq_hz;
    return HAL_OK;
}

/* Change la fréquence pendant que le moteur tourne. ARR s'applique tout de suite : si le compteur est déjà
 * près de la fin de la période on ne touche à rien (le compteur devrait faire le tour des 16 bits) et on
 * réessaie au prochain appel. Retourne 1 si la fréquence a été changée. */
static uint8_t change_freq(Stepper_HandleTypeDef *dev, uint32_t freq_hz)
{
    uint32_t periode = (STEPPER_TICK_HZ / freq_hz) - 1U;
    if (periode > 0xFFFFU)
    {
        return 0U;
    }
    if ((__HAL_TIM_GET_COUNTER(dev->htim) + 10U) >= periode)
    {
        return 0U;
    }

    __HAL_TIM_SET_AUTORELOAD(dev->htim, periode);
    __HAL_TIM_SET_COMPARE(dev->htim, dev->channel, (periode + 1U) / 2U);
    return 1U;
}

/* Durée (ms) pour faire "steps" pas : rampe linéaire de f0 à f1 sur STEPPER_RAMP_MS, puis f1 constant.
 * Si le déplacement est plus court que la rampe, tout se fait à f0 (*ramp = 0).
 * On coupe à (pas - 0,5) : le STEP démarre par un front montant (= 1 pas), puis un pas par période. Couper au
 * milieu de la dernière période garde le bon nombre de pas malgré l'incertitude de 1 ms de HAL_GetTick. */
static uint32_t move_time_ms(uint32_t steps, uint32_t f0, uint32_t f1, uint8_t *ramp)
{
    uint64_t target2 = (uint64_t)((2U * steps) - 1U) * 1000U;              /* (pas - 0,5) x 2000 */

    *ramp = 0U;
    if (f0 < f1)
    {
        uint64_t ramp2 = (uint64_t)(f0 + f1) * STEPPER_RAMP_MS;            /* pas de la rampe x 2000 */
        if (target2 > ramp2)
        {
            *ramp = 1U;
            return STEPPER_RAMP_MS + (uint32_t)((target2 - ramp2 + (2U * (uint64_t)f1)) / (2U * (uint64_t)f1));
        }
    }
    return (uint32_t)((target2 + (2U * (uint64_t)f0)) / (2U * (uint64_t)f0));
}

HAL_StatusTypeDef Stepper_Start(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t freq_hz)
{
    return start_at(dev, sens, freq_hz);
}

HAL_StatusTypeDef Stepper_Run(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t freq_hz)
{
    if ((dev == NULL) || (freq_hz == 0U))
    {
        return HAL_ERROR;
    }

    uint32_t f0 = (freq_hz > STEPPER_START_HZ) ? STEPPER_START_HZ : freq_hz;
    uint32_t t0 = HAL_GetTick();

    if (start_at(dev, sens, f0) != HAL_OK)
    {
        return HAL_ERROR;
    }

    if (f0 < freq_hz)
    {
        dev->ramping = 1U;
        dev->f_target = freq_hz;
        dev->t_ramp0 = t0;
    }
    return HAL_OK;
}

HAL_StatusTypeDef Stepper_Move(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t steps, uint32_t freq_hz)
{
    if ((dev == NULL) || (steps == 0U) || (freq_hz == 0U))
    {
        return HAL_ERROR;
    }

    uint32_t f0 = (freq_hz > STEPPER_START_HZ) ? STEPPER_START_HZ : freq_hz;
    uint8_t ramp;
    uint32_t ms = move_time_ms(steps, f0, freq_hz, &ramp);
    uint32_t t0 = HAL_GetTick();

    if (start_at(dev, sens, f0) != HAL_OK)
    {
        return HAL_ERROR;
    }

    dev->ramping = ramp;
    dev->f_target = freq_hz;
    dev->t_ramp0 = t0;
    dev->move_active = 1U;
    dev->t_move_end = t0 + ms;
    return HAL_OK;
}

HAL_StatusTypeDef Stepper_Stop(Stepper_HandleTypeDef *dev)
{
    if (dev == NULL)
    {
        return HAL_ERROR;
    }

    dev->running = 0U;
    dev->ramping = 0U;
    dev->move_active = 0U;
    return HAL_TIM_PWM_Stop(dev->htim, dev->channel);
}

void Stepper_Update(Stepper_HandleTypeDef *dev)
{
    if ((dev == NULL) || (dev->running == 0U))
    {
        return;
    }

    uint32_t now = HAL_GetTick();

    if ((dev->move_active != 0U) && ((int32_t)(now - dev->t_move_end) >= 0))
    {
        (void)Stepper_Stop(dev);                                           /* déplacement terminé */
        return;
    }

    if (dev->ramping != 0U)
    {
        uint32_t t = now - dev->t_ramp0;
        uint32_t f = dev->f_target;

        if (t < STEPPER_RAMP_MS)
        {
            f = STEPPER_START_HZ + (uint32_t)(((uint64_t)(dev->f_target - STEPPER_START_HZ) * t) / STEPPER_RAMP_MS);
        }

        if ((f != dev->f_now) && (change_freq(dev, f) != 0U))
        {
            dev->f_now = f;
        }

        if ((t >= STEPPER_RAMP_MS) && (dev->f_now == dev->f_target))
        {
            dev->ramping = 0U;
        }
    }
}

uint8_t Stepper_IsMoving(const Stepper_HandleTypeDef *dev)
{
    return ((dev != NULL) && (dev->running != 0U)) ? 1U : 0U;
}

HAL_StatusTypeDef Stepper_Rotate(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t steps, uint32_t freq_hz)
{
    if (Stepper_Move(dev, sens, steps, freq_hz) != HAL_OK)
    {
        return HAL_ERROR;
    }

    while (Stepper_IsMoving(dev) != 0U)
    {
        HAL_Delay(1U);
        Stepper_Update(dev);                                               /* rampe + arrêt à la fin */
    }

    return HAL_OK;
}

HAL_StatusTypeDef Stepper_RotateUntil(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t freq_hz,
                                      uint8_t (*stop)(void), uint32_t timeout_ms)
{
    if ((dev == NULL) || (stop == NULL))
    {
        return HAL_ERROR;
    }

    if (Stepper_Run(dev, sens, freq_hz) != HAL_OK)
    {
        return HAL_ERROR;
    }

    uint32_t t0 = HAL_GetTick();

    while (stop() == 0U)
    {
        Stepper_Update(dev);                                               /* rampe d'accélération */

        if ((uint32_t)(HAL_GetTick() - t0) >= timeout_ms)
        {
            (void)Stepper_Stop(dev);
            return HAL_TIMEOUT;
        }
    }

    return Stepper_Stop(dev);
}
