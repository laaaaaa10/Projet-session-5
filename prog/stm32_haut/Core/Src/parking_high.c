/*
 * parking_high.c
 *
 *  Created on: 25 nov. 2026
 *      Author: Javier Bolduc
 *
 */

#include "parking_high.h"
#include "clickboard_io_mux.h"
#include "inductive_sensor.h"
#include "stepper_motor.h"

static ClickBoard_HandleTypeDef      clickboard;
static InductiveSensor_HandleTypeDef inductive;
static uint8_t                       floor_sensor;   /* capteur visé : 0 (étage 1) à 2 (étage 3) */

/* Condition d'arrêt de l'ascenseur. */
static uint8_t at_floor(void)
{
    uint8_t seen = 0U;
    return ((InductiveSensor_Read(&inductive, floor_sensor, &seen) == HAL_OK) && (seen != 0U)) ? 1U : 0U;
}

/* Monte (PARKING_UP) ou descend (PARKING_DOWN) jusqu'à l'étage 1 à 3. HAL_OK, HAL_TIMEOUT ou HAL_ERROR. */
static HAL_StatusTypeDef __attribute__((unused)) go_to_floor(uint8_t floor, StepperSens_t dir)
{
    if ((floor < 1U) || (floor > PARKING_FLOOR_COUNT))
    {
        return HAL_ERROR;
    }
    floor_sensor = (uint8_t)(floor - 1U);
    return Stepper_RotateUntil(&stepper_height, dir, 250U, at_floor, 120000U);   /* sens, Hz, arrêt, timeout (ms) */
}

HAL_StatusTypeDef ParkingHigh_Init(I2C_HandleTypeDef *hi2c)
{
    if ((ClickBoard_InitPWM(&clickboard, hi2c) != HAL_OK) || (InductiveSensor_Init(&inductive, &clickboard) != HAL_OK))
    {
        return HAL_ERROR;
    }
    return HAL_OK;
}

void ParkingHigh_Process(void)
{
#if (PARKING_DEMO_LOOP != 0U)
    /* TEST : le plateau avance d'un emplacement (45 degrés), pause, puis revient. */
    Stepper_Rotate(&stepper_rotation, PARKING_FORWARD,  1000U, 280U);    /* sens, pas (2000 = 1 tour), Hz */
    HAL_Delay(3000U);
    Stepper_Rotate(&stepper_rotation, PARKING_BACKWARD, 1000U, 280U);
    HAL_Delay(3000U);
#endif
}

/* ---- Commandes : logique à écrire (pour l'instant elles répondent seulement "exécuté") ----
 * Exemple :  go_to_floor(2U, PARKING_UP);
 *            Stepper_Rotate(&stepper_rotation, PARKING_FORWARD, 500U, 200U); */

HAL_StatusTypeDef ParkingHigh_Home(void)
{
    /* TODO : aller aux fins de course (reed) pour établir la position de référence (ESA-09 / TI-02). */
    return HAL_OK;
}

HAL_StatusTypeDef ParkingHigh_Store(uint8_t space)
{
    (void)space;
    /* TODO : case (1 à 14) -> étage + emplacement, go_to_floor(), Stepper_Rotate(), bras (DriveMotor_*).
     * Refuser (HAL_ERROR) si la case est hors 1 à 14. */
    return HAL_OK;
}

HAL_StatusTypeDef ParkingHigh_Retrieve(uint8_t space)
{
    (void)space;
    /* TODO : même conversion que ParkingHigh_Store, puis ramener le véhicule à la remise. */
    return HAL_OK;
}

uint8_t ParkingHigh_IsBusy(void)
{
    /* TODO : 1 pendant un mouvement commandé, 0 sinon. */
    return 0U;
}
