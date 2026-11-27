/*
 * drive_motor.h
 *
 *  Created on: 26 nov. 2026
 *      Author: Javier Bolduc
 *
 * Moteur DC du bras (vérin) par un module L298N, canal A, cavalier ENA en place. Branchement : voir le README.
 */

#ifndef INC_DRIVE_MOTOR_H_
#define INC_DRIVE_MOTOR_H_

#include "stm32f4xx_hal.h"

/* 1 = PWM sur IN1, 0 = PWM sur IN2. Si le moteur tourne à l'envers du nom, inverser les deux valeurs. */
typedef enum
{
    DRIVEMOTOR_HORAIRE     = GPIO_PIN_SET,
    DRIVEMOTOR_ANTIHORAIRE = GPIO_PIN_RESET
} DriveMotorSens_t;

/* Configure PD12 (IN1) et PD13 (IN2) en PWM. Moteur arrêté. */
HAL_StatusTypeDef DriveMotor_Init(void);

/* Fait tourner le moteur. duty_percent : 1 à 100 (vitesse), 0 = arrêt. Non bloquant. */
HAL_StatusTypeDef DriveMotor_Run(DriveMotorSens_t sens, uint8_t duty_percent);

/* Arrête le moteur (IN1 = IN2 = 0 : frein). */
HAL_StatusTypeDef DriveMotor_Stop(void);

/* Déplace le bras (sens, vitesse 1 à 100 %) pendant duration_ms, puis l'arrête. BLOQUANT.
 * Aucun retour de position : position = vitesse x durée. */
HAL_StatusTypeDef DriveMotor_Move(DriveMotorSens_t sens, uint8_t duty_percent, uint32_t duration_ms);

#endif /* INC_DRIVE_MOTOR_H_ */
