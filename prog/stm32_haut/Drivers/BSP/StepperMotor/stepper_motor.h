/*
 * stepper_motor.h
 *
 *  Created on: 19 nov. 2026
 *      Author: Javier Bolduc
 */

#ifndef INC_STEPPER_MOTOR_H_
#define INC_STEPPER_MOTOR_H_

#include "stm32f4xx_hal.h"

/* Niveau envoyé sur DIR. Si le moteur tourne à l'envers du nom, inverser les deux valeurs. */
typedef enum
{
    STEPPER_HORAIRE     = GPIO_PIN_SET,
    STEPPER_ANTIHORAIRE = GPIO_PIN_RESET
} StepperSens_t;

/* Un moteur = un timer/canal PWM pour STEP + une broche DIR */
typedef struct
{
    TIM_HandleTypeDef *htim;      /* timer qui génère le STEP */
    uint32_t           channel;   /* canal PWM (TIM_CHANNEL_x) */
    GPIO_TypeDef      *dir_port;
    uint16_t           dir_pin;
    uint8_t            set;       /* jeu de broches (voir stepper_motor.c) */

    /* état interne, ne pas toucher */
    uint8_t            running;
    uint8_t            ramping;
    uint8_t            move_active;
    uint32_t           f_now;
    uint32_t           f_target;
    uint32_t           t_ramp0;
    uint32_t           t_move_end;
} Stepper_HandleTypeDef;

/* Les deux moteurs (définis dans stepper_motor.c) */
extern Stepper_HandleTypeDef stepper_rotation;
extern Stepper_HandleTypeDef stepper_height;

/* ---- Bloquantes (avec rampe d'accélération) ---- */

/* Tourne de N pas (sens, pas, pas/s), puis s'arrête. */
HAL_StatusTypeDef Stepper_Rotate(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t steps, uint32_t freq_hz);

/* Tourne jusqu'à ce que stop() retourne 1 (ex. : capteur). HAL_TIMEOUT après timeout_ms. */
HAL_StatusTypeDef Stepper_RotateUntil(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t freq_hz,
                                      uint8_t (*stop)(void), uint32_t timeout_ms);

/* ---- Non bloquantes : appeler Stepper_Update() souvent ---- */

/* Tourne jusqu'à Stepper_Stop, avec rampe. */
HAL_StatusTypeDef Stepper_Run(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t freq_hz);

/* N pas avec rampe, puis s'arrête tout seul (Stepper_IsMoving() repasse à 0). */
HAL_StatusTypeDef Stepper_Move(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t steps, uint32_t freq_hz);

/* Fréquence constante, sans rampe, jusqu'à Stepper_Stop. */
HAL_StatusTypeDef Stepper_Start(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t freq_hz);

HAL_StatusTypeDef Stepper_Stop(Stepper_HandleTypeDef *dev);
void              Stepper_Update(Stepper_HandleTypeDef *dev);
uint8_t           Stepper_IsMoving(const Stepper_HandleTypeDef *dev);

#endif /* INC_STEPPER_MOTOR_H_ */
