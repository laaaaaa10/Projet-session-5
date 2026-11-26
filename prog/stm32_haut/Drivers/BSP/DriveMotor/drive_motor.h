/*
 * drive_motor.h
 *
 *  Created on: 26 nov. 2026
 *      Author: Javier Bolduc
 *
 * Moteur DC du bras (vérin) par un module L298N, canal A. Branchement : voir le README.
 */

#ifndef INC_DRIVE_MOTOR_H_
#define INC_DRIVE_MOTOR_H_

#include "stm32f4xx_hal.h"

/* Niveau envoyé sur IN1 (IN2 reçoit l'inverse). Si le bras sort quand on demande de rentrer, inverser les deux. */
typedef enum
{
    DRIVEMOTOR_SORTIR  = GPIO_PIN_SET,
    DRIVEMOTOR_RENTRER = GPIO_PIN_RESET
} DriveMotorSens_t;

/* Configure PD12 (ENA, PWM), PD13 (IN1) et PD15 (IN2). Moteur arrêté. */
HAL_StatusTypeDef DriveMotor_Init(void);

/* Fait tourner le moteur. duty_percent : 1 à 100 (vitesse), 0 = arrêt. Non bloquant
 * (sauf 20 ms d'arrêt si le sens change en marche). */
HAL_StatusTypeDef DriveMotor_Run(DriveMotorSens_t sens, uint8_t duty_percent);

/* Arrête le moteur. */
HAL_StatusTypeDef DriveMotor_Stop(void);

/* Déplace le bras (sens, vitesse 1 à 100 %) pendant duration_ms, puis l'arrête. BLOQUANT.
 * Aucun retour de position : position = vitesse x durée. */
HAL_StatusTypeDef DriveMotor_Move(DriveMotorSens_t sens, uint8_t duty_percent, uint32_t duration_ms);

#endif /* INC_DRIVE_MOTOR_H_ */
