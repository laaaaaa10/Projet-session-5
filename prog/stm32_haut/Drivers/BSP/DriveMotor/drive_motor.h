/*
 * drive_motor.h
 *
 * Driver du moteur DC (micro-vérin du bras poussoir) par le drive PCB-02 (DRV8220, mode PH/EN).
 *
 * Branchement : connecteur J2 du PCB-02 -> PMOD "pont en H" P13 de la carte PCB-12
 *   P13 pin 1 = DIR = PD13 (sortie GPIO)         -> DIR
 *   P13 pin 2 = EN  = PD12 (TIM4 CH1, PWM 20 kHz) -> Motor_ON
 *   + masse commune entre la carte STM32 et le PCB-02
 */

#ifndef INC_DRIVE_MOTOR_H_
#define INC_DRIVE_MOTOR_H_

#include "stm32f4xx_hal.h"

/* Sens du moteur : niveau envoyé sur DIR.
 * Si le bras sort quand on demande de rentrer, inverser les deux valeurs ici. */
typedef enum
{
    DRIVEMOTOR_SORTIR  = GPIO_PIN_SET,
    DRIVEMOTOR_RENTRER = GPIO_PIN_RESET
} DriveMotorSens_t;

/* Configure PD12 (PWM) et PD13 (DIR). Moteur arrêté à la fin. À appeler une fois au démarrage. */
HAL_StatusTypeDef DriveMotor_Init(void);

/* Fait tourner le moteur. duty_percent : 1 à 100 (vitesse). 0 = arrêt.
 * Si le sens change pendant que le moteur tourne, il est arrêté 20 ms avant d'inverser. Non bloquant sinon. */
HAL_StatusTypeDef DriveMotor_Run(DriveMotorSens_t sens, uint8_t duty_percent);

/* Arrête le moteur (Motor_ON à 0). */
HAL_StatusTypeDef DriveMotor_Stop(void);

#endif /* INC_DRIVE_MOTOR_H_ */
