/*
 * stepper.h
 *
 *  Created on: 19 nov. 2026
 *      Author: Jonathan Marois
 */

#ifndef INC_STEPPER_MOTOR_H_
#define INC_STEPPER_MOTOR_H_

#include "stm32f4xx_hal.h"

/* Fréquence de comptage des timers de STEP : 84 MHz / (PSC 83 + 1) = 1 MHz */
#define STEPPER_TICK_HZ  1000000U

/* Sens de rotation : niveau envoyé sur la broche DIR du drive.
 * Si le moteur tourne à l'envers du nom, inverser les deux valeurs ici. */
typedef enum
{
    STEPPER_HORAIRE     = GPIO_PIN_SET,
    STEPPER_ANTIHORAIRE = GPIO_PIN_RESET
} StepperSens_t;

/* Un moteur = un timer/canal PWM pour STEP + une broche DIR */
typedef struct
{
    TIM_HandleTypeDef *htim;      /* timer qui génère le STEP */
    uint32_t           channel;   /* canal PWM du timer (TIM_CHANNEL_x) */
    GPIO_TypeDef      *dir_port;  /* port de la broche DIR */
    uint16_t           dir_pin;   /* broche DIR */
} Stepper_HandleTypeDef;

/* Les deux moteurs, déjà prêts (définis dans stepper.c) */
extern Stepper_HandleTypeDef stepper_rotation;
extern Stepper_HandleTypeDef stepper_height;

HAL_StatusTypeDef Stepper_Rotate(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t steps, uint32_t freq_hz);

#endif /* INC_STEPPER_MOTOR_H_ */
