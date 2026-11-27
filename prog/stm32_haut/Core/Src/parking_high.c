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
#include "drive_motor.h"

static ClickBoard_HandleTypeDef      clickboard;
static InductiveSensor_HandleTypeDef inductive;
static uint8_t                       floor_sensor;        /* capteur visé : 0 à 2 */
static uint8_t                       current_floor;       /* 0 = inconnu */
static uint8_t                       current_slot = 1U;   /* pas de capteur sur le plateau : 1 au démarrage */
static volatile uint8_t              busy;

static uint8_t at_floor(void)
{
    uint8_t seen = 0U;

    (void)InductiveSensor_Read(&inductive, floor_sensor, &seen);
    return seen;
}

/* Étage inconnu : descend. */
static HAL_StatusTypeDef go_to_floor(uint8_t floor)
{
    StepperSens_t sens = ((current_floor != 0U) && (floor > current_floor)) ? STEPPER_ANTIHORAIRE : STEPPER_HORAIRE;   /* ANTIHORAIRE = monte, à confirmer */
    HAL_StatusTypeDef status;

    if (floor == current_floor)
    {
        return HAL_OK;
    }
    floor_sensor = (uint8_t)(floor - 1U);
    status = Stepper_RotateUntil(&stepper_height, sens, 167U, at_floor, 120000U);   /* sens, Hz, arrêt, timeout (ms) */
    current_floor = (status == HAL_OK) ? floor : 0U;
    return status;
}

static void rotate_to_slot(uint8_t slot)
{
    int16_t diff = (int16_t)slot - (int16_t)current_slot;

    if (diff < 0)
    {
        diff += (int16_t)(PARKING_SLOTS_PER_FLOOR + 1U);   /* + le secteur vide */
    }
    if (diff != 0)
    {
        (void)Stepper_Rotate(&stepper_rotation, STEPPER_HORAIRE, (uint32_t)diff * 500U, 400U);   /* 500 pas = 1 emplacement (demi-pas), Hz */
    }
    current_slot = slot;
}

/* Case 1-7 -> étage 2, case 8-14 -> étage 3. */
static uint8_t space_floor(uint8_t space)
{
    return (uint8_t)(2U + ((space - 1U) / PARKING_SLOTS_PER_FLOOR));
}

static uint8_t space_slot(uint8_t space)
{
    return (uint8_t)(((space - 1U) % PARKING_SLOTS_PER_FLOOR) + 1U);
}

HAL_StatusTypeDef ParkingHigh_Init(I2C_HandleTypeDef *hi2c)
{
    if (ClickBoard_InitPWM(&clickboard, hi2c) != HAL_OK)
    {
        return HAL_ERROR;
    }
    return InductiveSensor_Init(&inductive, &clickboard);
}

void ParkingHigh_Process(void)
{
}

HAL_StatusTypeDef ParkingHigh_Home(void)
{
    HAL_StatusTypeDef status;

    busy = 1U;
    current_floor = 0U;
    status = go_to_floor(1U);
    busy = 0U;
    return status;
}

HAL_StatusTypeDef ParkingHigh_Store(uint8_t space)
{
    HAL_StatusTypeDef status;

    if ((current_floor == 0U) || (space < 1U) || (space > PARKING_SPACE_COUNT))
    {
        return HAL_ERROR;
    }

    busy = 1U;
    status = go_to_floor(1U);
    if (status == HAL_OK) { status = DriveMotor_Move(DRIVEMOTOR_ANTIHORAIRE, 80U, 4500U); }   /* prend la voiture au quai */
    if (status == HAL_OK) { status = go_to_floor(space_floor(space)); }
    if (status == HAL_OK) { rotate_to_slot(space_slot(space)); }
    if (status == HAL_OK) { status = DriveMotor_Move(DRIVEMOTOR_HORAIRE, 80U, 4500U); }       /* pousse la voiture dans l'emplacement */
    busy = 0U;
    return status;
}

HAL_StatusTypeDef ParkingHigh_Retrieve(uint8_t space)
{
    HAL_StatusTypeDef status;

    if ((current_floor == 0U) || (space < 1U) || (space > PARKING_SPACE_COUNT))
    {
        return HAL_ERROR;
    }

    busy = 1U;
    status = go_to_floor(space_floor(space));
    if (status == HAL_OK) { rotate_to_slot(space_slot(space)); }
    if (status == HAL_OK) { status = DriveMotor_Move(DRIVEMOTOR_ANTIHORAIRE, 80U, 4500U); }   /* reprend la voiture de l'emplacement */
    if (status == HAL_OK) { status = go_to_floor(1U); }
    if (status == HAL_OK) { status = DriveMotor_Move(DRIVEMOTOR_HORAIRE, 80U, 4500U); }       /* sort la voiture au quai */
    busy = 0U;
    return status;
}

uint8_t ParkingHigh_IsBusy(void)
{
    return busy;
}
