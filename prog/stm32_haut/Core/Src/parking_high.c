/*
 * parking_high.c
 *
 *  Created on: 25 nov. 2026
 *      Author: Layten
 *
 * Voir parking_high.h pour la séquence et les réglages.
 */

#include "parking_high.h"
#include "clickboard_io_mux.h"
#include "inductive_sensor.h"
#include "stepper_motor.h"

typedef enum
{
    STATE_IDLE = 0,    /* rien à faire (PARKING_DEMO_LOOP = 0 : on attend les commandes) */
    STATE_START,       /* initialisé, le premier Process lance la descente vers l'étage 1 */
    STATE_MOVING,      /* hauteur en mouvement vers floor_target */
    STATE_ROTATING,    /* hauteur arrêtée, plateau qui tourne vers l'emplacement suivant */
    STATE_WAITING,     /* plateau en place, attente de la fin de la pause à l'étage */
    STATE_FAULT        /* moteurs arrêtés */
} State_t;

static ClickBoard_HandleTypeDef      clickboard;
static InductiveSensor_HandleTypeDef inductive;

static State_t             state = STATE_FAULT;
static ParkingHigh_Error_t error = PARKING_HIGH_ERR_INIT;

static uint8_t  floor_now;      /* 0 = inconnu, sinon 1 à PARKING_FLOOR_COUNT */
static uint8_t  floor_target;
static uint8_t  going_up;       /* 1 = la séquence monte, 0 = elle descend */
static uint8_t  space_idx;      /* 0 à PARKING_SPACE_COUNT - 1 (emplacement 1 = 0) */
static uint8_t  rot_forward;    /* 1 = emplacement 1 vers 7, 0 = 7 vers 1 */
static uint8_t  confirm;        /* lectures consécutives "détecté" */
static uint8_t  sensor_fail;    /* erreurs I2C consécutives */
static uint32_t t_move;         /* début du déplacement en hauteur */
static uint32_t t_arrival;      /* arrêt à l'étage */

static StepperSens_t opposite(StepperSens_t sens)
{
    return (sens == STEPPER_HORAIRE) ? STEPPER_ANTIHORAIRE : STEPPER_HORAIRE;
}

/* Position d'un emplacement en pas depuis l'emplacement 1. Calculée en absolu (arrondie) :
 * l'aller et le retour passent par exactement les mêmes positions, aucune dérive. */
static uint32_t space_position(uint8_t space)
{
    return (((uint32_t)space * PARKING_ROTATION_STEPS_PER_REV) + (PARKING_SECTOR_COUNT / 2U)) / PARKING_SECTOR_COUNT;
}

static void fault(ParkingHigh_Error_t code)
{
    (void)Stepper_Stop(&stepper_height);
    (void)Stepper_Stop(&stepper_rotation);
    error = code;
    state = STATE_FAULT;
}

/* Hauteur arrêtée sur l'étage visé : le plateau passe à l'emplacement suivant. */
static void start_rotation(void)
{
    if ((rot_forward != 0U) && (space_idx == (PARKING_SPACE_COUNT - 1U)))
    {
        rot_forward = 0U;     /* dernier emplacement : on repart dans l'autre sens */
    }
    else if ((rot_forward == 0U) && (space_idx == 0U))
    {
        rot_forward = 1U;
    }

    uint8_t next = (rot_forward != 0U) ? (uint8_t)(space_idx + 1U) : (uint8_t)(space_idx - 1U);
    uint32_t from = space_position(space_idx);
    uint32_t to   = space_position(next);
    uint32_t steps = (to > from) ? (to - from) : (from - to);

    StepperSens_t dir = (rot_forward != 0U) ? PARKING_ROTATION_DIR_FORWARD : opposite(PARKING_ROTATION_DIR_FORWARD);
    if (Stepper_Move(&stepper_rotation, dir, steps, PARKING_ROTATION_FREQ_HZ) != HAL_OK)
    {
        fault(PARKING_HIGH_ERR_MOTOR);
        return;
    }

    space_idx = next;
    state = STATE_ROTATING;
}

static void arrive(uint32_t now)
{
    (void)Stepper_Stop(&stepper_height);
    floor_now = floor_target;
    t_arrival = now;
    start_rotation();
}

/* Lance le déplacement en hauteur vers un étage (sens selon going_up). */
static void begin_move(uint8_t target, uint32_t now)
{
    floor_target = target;
    confirm = 0U;
    sensor_fail = 0U;
    t_move = now;
    state = STATE_MOVING;

    uint8_t present = 0U;
    if ((InductiveSensor_Read(&inductive, (uint8_t)(target - 1U), &present) == HAL_OK) && (present != 0U))
    {
        arrive(now);          /* déjà sur le capteur de l'étage visé */
        return;
    }

    StepperSens_t dir = (going_up != 0U) ? PARKING_HEIGHT_DIR_UP : opposite(PARKING_HEIGHT_DIR_UP);
    if (Stepper_Run(&stepper_height, dir, PARKING_HEIGHT_FREQ_HZ) != HAL_OK)
    {
        fault(PARKING_HIGH_ERR_MOTOR);
    }
}

/* Étage suivant de la séquence 1 -> 2 -> 3 -> 2 -> 1 -> 2 ... */
static uint8_t next_floor(void)
{
    if (going_up != 0U)
    {
        if (floor_now >= PARKING_FLOOR_COUNT)
        {
            going_up = 0U;
            return (uint8_t)(floor_now - 1U);
        }
        return (uint8_t)(floor_now + 1U);
    }

    if (floor_now <= 1U)
    {
        going_up = 1U;
        return (uint8_t)(floor_now + 1U);
    }
    return (uint8_t)(floor_now - 1U);
}

static void moving_step(uint32_t now)
{
    uint8_t present = 0U;

    Stepper_Update(&stepper_height);                  /* accélération progressive */

    if (InductiveSensor_Read(&inductive, (uint8_t)(floor_target - 1U), &present) != HAL_OK)
    {
        sensor_fail++;
        if (sensor_fail >= PARKING_SENSOR_FAIL_MAX)
        {
            fault(PARKING_HIGH_ERR_SENSOR);
            return;
        }
    }
    else
    {
        sensor_fail = 0U;
        confirm = (present != 0U) ? (uint8_t)(confirm + 1U) : 0U;
        if (confirm >= PARKING_FLOOR_CONFIRM_READS)
        {
            arrive(now);
            return;
        }
    }

    if ((uint32_t)(now - t_move) >= PARKING_HEIGHT_TIMEOUT_MS)
    {
        fault(PARKING_HIGH_ERR_TIMEOUT);
    }
}

HAL_StatusTypeDef ParkingHigh_Init(I2C_HandleTypeDef *hi2c)
{
    state = STATE_FAULT;
    error = PARKING_HIGH_ERR_INIT;

    if (ClickBoard_InitPWM(&clickboard, hi2c) != HAL_OK)
    {
        return HAL_ERROR;
    }
    if (InductiveSensor_Init(&inductive, &clickboard) != HAL_OK)
    {
        return HAL_ERROR;
    }

    floor_now = 0U;
    going_up = 0U;
    space_idx = 0U;
    rot_forward = 1U;
    error = PARKING_HIGH_OK;
    state = (PARKING_DEMO_LOOP != 0U) ? STATE_START : STATE_IDLE;
    return HAL_OK;
}

void ParkingHigh_Process(void)
{
    uint32_t now = HAL_GetTick();

    switch (state)
    {
    case STATE_IDLE:
        break;

    case STATE_START:
        begin_move(1U, now);                      /* descend jusqu'au capteur 1 */
        break;

    case STATE_MOVING:
        moving_step(now);
        break;

    case STATE_ROTATING:
        Stepper_Update(&stepper_rotation);            /* accélération, puis arrêt à la fin des pas */
        if (Stepper_IsMoving(&stepper_rotation) == 0U)
        {
            state = STATE_WAITING;
        }
        break;

    case STATE_WAITING:
        if ((uint32_t)(now - t_arrival) >= PARKING_FLOOR_DWELL_MS)
        {
            begin_move(next_floor(), now);
        }
        break;

    case STATE_FAULT:
    default:
        break;
    }
}

uint8_t ParkingHigh_GetFloor(void)
{
    return floor_now;
}

uint8_t ParkingHigh_GetSpace(void)
{
    return (uint8_t)(space_idx + 1U);
}

ParkingHigh_Error_t ParkingHigh_GetError(void)
{
    return error;
}

/* ======================================================================
 * COMMANDES (points d'entrée) : LA LOGIQUE MOTEUR EST À ÉCRIRE ICI
 * (rien n'est fait pour l'instant, les fonctions répondent seulement "accepté")
 * ====================================================================== */

HAL_StatusTypeDef ParkingHigh_Home(void)
{
    /* TODO : initialisation des axes (ESA-09 / TI-02) : aller aux fins de course (reed) pour établir la
     * position de référence, sans collision. Refuser (HAL_ERROR) si un mouvement est déjà en cours. */
    return HAL_OK;
}

HAL_StatusTypeDef ParkingHigh_Store(uint8_t space)
{
    (void)space;
    /* TODO : ranger un véhicule dans la case "space" (1 à 14).
     *   1. convertir la case en niveau + emplacement du plateau (7 par niveau, par exemple
     *      emplacement = ((space - 1) % 7) + 1 et niveau = (space - 1) / 7), et choisir quel capteur d'étage
     *      correspond à ce niveau (tableau à définir)
     *   2. aller chercher le véhicule à l'entrée, monter à l'étage, tourner le plateau, sortir le bras
     *      (DriveMotor_*), déposer, rentrer le bras
     *   3. refuser (HAL_ERROR) si occupé ou si la case est hors 1 à 14 */
    return HAL_OK;
}

HAL_StatusTypeDef ParkingHigh_Retrieve(uint8_t space)
{
    (void)space;
    /* TODO : récupérer le véhicule de la case "space" (1 à 14) et le ramener à la
     * position de remise à l'usager. Même conversion case -> niveau + emplacement que ParkingHigh_Store.
     * Refuser (HAL_ERROR) si occupé. */
    return HAL_OK;
}

uint8_t ParkingHigh_IsBusy(void)
{
    /* TODO : retourner 1 tant qu'un mouvement commandé est en cours, 0 sinon. */
    return 0U;
}
