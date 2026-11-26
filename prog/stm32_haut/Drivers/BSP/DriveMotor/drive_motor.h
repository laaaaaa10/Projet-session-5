/*
 * drive_motor.h
 *
 *  Created on: 26 nov. 2026
 *      Author: Layten
 *
 * Driver du moteur DC (micro-vérin du bras poussoir) par un module L298N (pont en H), canal A.
 * (Remplace le PCB-02 / DRV8220 qui était en panne.)
 *
 * Branchement : PMOD "pont en H" P13 de la carte PCB-12 -> module L298N
 *   P13 pin 2 = EN  = PD12 (TIM4 CH1, PWM)   -> ENA   (enlever le cavalier ENA du module)
 *   P13 pin 1 = DIR = PD13 (sortie GPIO)     -> IN1
 *   P13 pin 3 = PD15 (sortie GPIO)           -> IN2
 *   GND (n'importe quelle broche GND de la carte, P13 pin 5 probablement : à vérifier au multimètre)
 *                                            -> GND du module (masse commune obligatoire)
 *   Moteur sur OUT1 / OUT2. Alimentation 12 V sur la borne 12V, GND sur la borne GND.
 *   P13 pin 3 = SenseA sur le schéma (nom hérité de l'ancien drive) : ici simplement utilisée comme sortie IN2.
 *   Les broches IN3, IN4, ENB, la borne 5V et P13 pin 4 (PD14) ne sont pas utilisées.
 */

#ifndef INC_DRIVE_MOTOR_H_
#define INC_DRIVE_MOTOR_H_

#include "stm32f4xx_hal.h"

/* Sens du moteur : niveau envoyé sur IN1 (IN2 reçoit toujours l'inverse).
 * Si le bras sort quand on demande de rentrer, inverser les deux valeurs ici
 * (ou inverser les deux fils du moteur sur OUT1 / OUT2). */
typedef enum
{
    DRIVEMOTOR_SORTIR  = GPIO_PIN_SET,
    DRIVEMOTOR_RENTRER = GPIO_PIN_RESET
} DriveMotorSens_t;

/* Configure PD12 (PWM), PD13 (IN1) et PD15 (IN2). Moteur arrêté à la fin. À appeler une fois au démarrage. */
HAL_StatusTypeDef DriveMotor_Init(void);

/* Fait tourner le moteur. duty_percent : 1 à 100 (vitesse). 0 = arrêt.
 * Si le sens change pendant que le moteur tourne, il est arrêté 20 ms avant d'inverser. Non bloquant sinon.
 * Le L298N perd environ 2 V : le vérin reçoit environ 10 V pour une alimentation de 12 V, donc utiliser 100 %
 * si le bras manque de force. En dessous d'environ 20 %, le moteur ne démarre généralement pas. */
HAL_StatusTypeDef DriveMotor_Run(DriveMotorSens_t sens, uint8_t duty_percent);

/* Arrête le moteur (ENA à 0 : le pont est coupé). */
HAL_StatusTypeDef DriveMotor_Stop(void);

/* Équivalent de Stepper_Rotate : déplace le bras dans un sens à une vitesse (duty_percent, 1 à 100)
 * pendant duration_ms, puis l'arrête. BLOQUANT (HAL_Delay).
 * Le vérin n'a aucun retour de position : la position atteinte = vitesse x durée.
 * Course 102 mm, 53 mm/s à vide et 26 mm/s en charge (à 12 V) : course complète = environ 2 à 4 s,
 * un peu plus avec la perte du L298N. Il s'arrête tout seul en bout de course (détection de courant). */
HAL_StatusTypeDef DriveMotor_Move(DriveMotorSens_t sens, uint8_t duty_percent, uint32_t duration_ms);

#endif /* INC_DRIVE_MOTOR_H_ */
