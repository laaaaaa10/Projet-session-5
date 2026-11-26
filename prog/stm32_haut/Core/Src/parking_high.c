/*
 * parking_high.c
 *
 *  Created on: 25 nov. 2026
 *      Author: Layten
 *
 * Voir parking_high.h pour les réglages.
 */

#include "parking_high.h"
#include "clickboard_io_mux.h"
#include "inductive_sensor.h"
#include "stepper_motor.h"

static ClickBoard_HandleTypeDef      clickboard;
static InductiveSensor_HandleTypeDef inductive;
static uint8_t                       ready;          /* 1 = prêt, 0 = Init raté ou séquence arrêtée par un échec */
static uint8_t                       floor_sensor;   /* capteur de l'étage visé : 0 (étage 1) à 2 (étage 3) */

/* Condition d'arrêt de l'ascenseur : le capteur de l'étage visé le voit. */
static uint8_t at_floor(void)
{
    uint8_t seen = 0U;
    return ((InductiveSensor_Read(&inductive, floor_sensor, &seen) == HAL_OK) && (seen != 0U)) ? 1U : 0U;
}

/* Monte (PARKING_UP) ou descend (PARKING_DOWN) jusqu'à l'étage 1 à 3.
 * HAL_ERROR si l'étage n'est pas atteint dans PARKING_HEIGHT_TIMEOUT_MS (le moteur est alors arrêté). */
static HAL_StatusTypeDef __attribute__((unused)) go_to_floor(uint8_t floor, StepperSens_t dir)
{
    if ((floor < 1U) || (floor > PARKING_FLOOR_COUNT))
    {
        return HAL_ERROR;
    }
    floor_sensor = (uint8_t)(floor - 1U);
    return Stepper_RotateUntil(&stepper_height, dir, PARKING_HEIGHT_HZ, at_floor, PARKING_HEIGHT_TIMEOUT_MS);
}

HAL_StatusTypeDef ParkingHigh_Init(I2C_HandleTypeDef *hi2c)
{
    ready = 0U;
    if ((ClickBoard_InitPWM(&clickboard, hi2c) != HAL_OK) || (InductiveSensor_Init(&inductive, &clickboard) != HAL_OK))
    {
        return HAL_ERROR;
    }
    ready = 1U;
    return HAL_OK;
}

#if (PARKING_DEMO_LOOP != 0U)




/* TEST : va à un étage, avance ou recule le plateau d'un emplacement, puis pause. */
static HAL_StatusTypeDef demo_step(uint8_t floor, StepperSens_t height_dir, StepperSens_t rotation_dir)
{
    if (Stepper_Rotate(&stepper_rotation, rotation_dir, PARKING_SPACE_STEPS, PARKING_ROTATION_HZ) != HAL_OK)
    {
        return HAL_ERROR;
    }
    HAL_Delay(PARKING_DWELL_MS);
    return HAL_OK;
}

#endif

void ParkingHigh_Process(void)
{
#if (PARKING_DEMO_LOOP != 0U)
    if (ready == 0U)
    {
        return;
    }
#endif
}

/* ======================= COMMANDES : LA LOGIQUE EST À ÉCRIRE ICI =======================
 * (rien n'est fait pour l'instant, les fonctions répondent seulement "exécuté")
 * Exemple :  go_to_floor(2U, PARKING_UP);
 *            Stepper_Rotate(&stepper_rotation, PARKING_FORWARD, 2U * PARKING_SPACE_STEPS, PARKING_ROTATION_HZ); */

HAL_StatusTypeDef ParkingHigh_Home(void)
{
    /* TODO : initialisation des axes (ESA-09 / TI-02) : aller aux fins de course (reed) pour établir la
     * position de référence, sans collision. */
    return HAL_OK;
}

HAL_StatusTypeDef ParkingHigh_Store(uint8_t space)
{
    (void)space;
    /* TODO : ranger un véhicule dans la case "space" (1 à 14).
     *   1. convertir la case en étage + emplacement du plateau (par exemple 7 par étage)
     *   2. aller chercher le véhicule à l'entrée, go_to_floor(), Stepper_Rotate(), sortir le bras
     *      (DriveMotor_*), déposer, rentrer le bras
     *   3. refuser (HAL_ERROR) si la case est hors 1 à 14 */
    return HAL_OK;
}

HAL_StatusTypeDef ParkingHigh_Retrieve(uint8_t space)
{
    (void)space;
    /* TODO : récupérer le véhicule de la case "space" (1 à 14) et le ramener à la position de remise à
     * l'usager. Même conversion case -> étage + emplacement que ParkingHigh_Store. */
    return HAL_OK;
}

uint8_t ParkingHigh_IsBusy(void)
{
    /* TODO : retourner 1 tant qu'un mouvement commandé est en cours, 0 sinon. */
    return 0U;
}