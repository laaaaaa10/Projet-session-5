/*
 * t06_pcb04.h
 *
 *  Created on: 25 nov. 2026
 *      Author: William MacDonald (T06)
 *
 * Interface T06_Carte pour une ClickBoard PCB-04 en mode PWM, avec le pilote
 * de l'enseignant (Drivers/BSP/ClickBoard_IO_MUX et TCA6416A, J. Marois) :
 *   - TCA6416A à l'adresse 0x20 (TCA6416A_ADDR_PWM : interrupteur ADR_IO ouvert) ;
 *   - P1.0-P1.2 = canal du TMUX1308, P1.3 = EN_B (ClickBoard_SelectChannel / DisableMux) ;
 *   - P0.0-P0.7 = sorties des 8 récepteurs IR (entrées du TCA6416A) ;
 *   - PWM 38 kHz du MikroBus démarré ici (MB1 : TIM3 CH4 / PB1, MB2 : TIM2 CH2 / PA1).
 * Sur la PCB-04, le cavalier à souder « PWM » doit être fermé, « AN » et « AN0 » ouverts.
 */

#ifndef INC_T06_PCB04_H_
#define INC_T06_PCB04_H_

#include <stdbool.h>
#include "stm32f4xx_hal.h"
#include "clickboard_io_mux.h"
#include "t06_ir.h"

typedef struct
{
    ClickBoard_HandleTypeDef cb;
    I2C_HandleTypeDef       *hi2c;
    TIM_HandleTypeDef       *htim;
    uint32_t                 canal_tim;
    bool                     pret;               /* carte configurée et joignable */
    bool                     pwm_demarre;
    uint8_t                  echecs_consecutifs; /* échecs I2C de suite */
    uint32_t                 t_prochain_essai;   /* prochaine tentative d'initialisation */
    uint32_t                 reprises;           /* réinitialisations réussies après une panne */
} T06_Pcb04;

/* Libère le bus I2C s'il est bloqué, initialise la carte (multiplexeur désactivé,
 * port 0 en entrées) et démarre le PWM. Si la carte ne répond pas, ou après 3 échecs
 * I2C de suite en fonctionnement, une nouvelle initialisation est tentée au plus une
 * fois par seconde ; entre-temps T06 compte des erreurs et déclare l'état non fiable. */
bool T06_Pcb04_Init(T06_Pcb04 *carte, I2C_HandleTypeDef *hi2c, TIM_HandleTypeDef *htim, uint32_t canal_tim);

/* Interface à passer à T06_Init. */
T06_Carte T06_Pcb04_Interface(T06_Pcb04 *carte);

#endif /* INC_T06_PCB04_H_ */
