/*
 * stepper.h
 *
 *  Created on: 19 nov. 2026
 *      Author: Layten
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

/* Accélération : un pas-à-pas lancé directement à grande vitesse cale ou vibre (le couple tombe quand la
 * vitesse monte). Les déplacements démarrent donc à STEPPER_START_HZ et montent linéairement jusqu'à la
 * fréquence demandée en STEPPER_RAMP_MS. Si le moteur cale encore : baisser la fréquence demandée, ou
 * STEPPER_START_HZ, ou allonger STEPPER_RAMP_MS. */
#define STEPPER_START_HZ  120U
#define STEPPER_RAMP_MS   400U

/* Un moteur = un timer/canal PWM pour STEP + une broche DIR */
typedef struct
{
    TIM_HandleTypeDef *htim;      /* timer qui génère le STEP */
    uint32_t           channel;   /* canal PWM du timer (TIM_CHANNEL_x) */
    GPIO_TypeDef      *dir_port;  /* port de la broche DIR */
    uint16_t           dir_pin;   /* broche DIR */
    uint8_t            set;       /* jeu de broches utilisé (voir stepper_motor.c) */

    /* --- état interne, ne pas toucher --- */
    uint8_t            running;
    uint8_t            ramping;
    uint8_t            move_active;
    uint32_t           f_now;
    uint32_t           f_target;
    uint32_t           t_ramp0;
    uint32_t           t_move_end;
} Stepper_HandleTypeDef;

/* Les deux moteurs, déjà prêts (définis dans stepper.c) */
extern Stepper_HandleTypeDef stepper_rotation;
extern Stepper_HandleTypeDef stepper_height;

/* Déplacement BLOQUANT de N pas (avec rampe d'accélération), puis arrêt. */
HAL_StatusTypeDef Stepper_Rotate(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t steps, uint32_t freq_hz);

/* --- Versions NON bloquantes (le programme continue pendant que le moteur tourne) ---
 * Stepper_Update() doit être appelé souvent (boucle principale) : il fait avancer la rampe et arrête
 * le moteur à la fin d'un Stepper_Move. */

/* Tourne jusqu'à Stepper_Stop, avec rampe d'accélération (ex. : jusqu'à un capteur). */
HAL_StatusTypeDef Stepper_Run(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t freq_hz);

/* Fait N pas avec rampe d'accélération, puis s'arrête tout seul (Stepper_IsMoving() repasse à 0). */
HAL_StatusTypeDef Stepper_Move(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t steps, uint32_t freq_hz);

/* Tourne à fréquence constante, sans rampe, jusqu'à Stepper_Stop. */
HAL_StatusTypeDef Stepper_Start(Stepper_HandleTypeDef *dev, StepperSens_t sens, uint32_t freq_hz);

HAL_StatusTypeDef Stepper_Stop(Stepper_HandleTypeDef *dev);
void              Stepper_Update(Stepper_HandleTypeDef *dev);
uint8_t           Stepper_IsMoving(const Stepper_HandleTypeDef *dev);

#endif /* INC_STEPPER_MOTOR_H_ */
