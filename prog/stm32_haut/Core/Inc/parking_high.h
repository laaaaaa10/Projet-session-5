/*
 * parking_high.h
 *
 *  Created on: 25 nov. 2026
 *      Author: Layten
 *
 * Logique du stationnement haut (STM32 HAUT) : ascenseur (3 étages, capteurs inductifs) + plateau tournant
 * (7 emplacements répartis sur 8 secteurs de 45 degrés, le 8e secteur est vide).
 *
 * Séquence (en boucle) :
 *   - hauteur : étage 1 -> 2 -> 3 -> 2 -> 1 -> 2 ...  (arrêt sur le capteur de l'étage visé, pause à chaque étage)
 *   - à chaque arrêt en hauteur, le plateau tourne d'un emplacement (45 degrés)
 *   - plateau : emplacement 1 -> 7 dans le sens "avant", puis 7 -> 1 dans le sens inverse, et ainsi de suite
 *     (jamais de tour complet, les fils ne s'enroulent pas ; le secteur vide n'est jamais traversé)
 *
 * Au démarrage : le plateau doit être sur l'emplacement 1. La hauteur n'a pas besoin d'être à un endroit précis
 * (elle descend jusqu'au capteur 1).
 *
 * Intégration dans main.c (rien d'autre à faire) :
 *     ParkingHigh_Init(&hi2c1);          une fois, après les MX_..._Init
 *     ParkingHigh_Process();             dans while(1), sans bloquer
 */

#ifndef INC_PARKING_HIGH_H_
#define INC_PARKING_HIGH_H_

#include "stm32f4xx_hal.h"
#include "stepper_motor.h"

/* ============================== RÉGLAGES ============================== */

/* 1 = boucle de TEST au démarrage (étages 1-2-3-2-1 + rotation, voir plus haut).
 * 0 = rien ne bouge tout seul : les mouvements viennent des commandes ParkingHigh_Home / Store / Retrieve. */
#define PARKING_DEMO_LOOP                1U

/* Vitesses (pas par seconde) en régime établi. Au départ, chaque moteur accélère progressivement :
 * voir STEPPER_START_HZ et STEPPER_RAMP_MS dans stepper_motor.h. Moteur qui cale ou manque de force : baisser. */

/* --- Plateau tournant --- */
/* Nombre de pas pour UN TOUR COMPLET du plateau. Un emplacement = ce nombre / 8.
 * 8000 = 5 x l'ancienne valeur (1600) : le plateau ne tournait pas assez. Valeur à affiner sur le banc :
 * si le plateau avance de trop (ou pas assez) d'un emplacement, nouvelle valeur = ancienne x (voulu / mesuré). */
#define PARKING_ROTATION_STEPS_PER_REV   8000U
/* Vitesse du plateau (pas/s). Plus bas = plus de force, mais plus lent (1 emplacement = 1000 pas). */
#define PARKING_ROTATION_FREQ_HZ         300U
/* Sens de la rotation de l'emplacement 1 vers l'emplacement 7. Si le plateau part vers le secteur vide, inverser. */
#define PARKING_ROTATION_DIR_FORWARD     STEPPER_HORAIRE

/* --- Hauteur --- */
#define PARKING_HEIGHT_FREQ_HZ           400U
/* Sens "monter". Si l'ascenseur descend quand il devrait monter, mettre STEPPER_HORAIRE. */
#define PARKING_HEIGHT_DIR_UP            STEPPER_ANTIHORAIRE
/* Temps maximum pour atteindre un étage : au-delà, tout s'arrête (mauvais sens, capteur débranché, bloqué...). */
#define PARKING_HEIGHT_TIMEOUT_MS        60000U

/* --- Étages --- */
#define PARKING_FLOOR_COUNT              3U        /* capteurs 1 (bas) à 3 (haut) */
#define PARKING_FLOOR_DWELL_MS           3000U     /* durée minimale de l'arrêt à chaque étage */
#define PARKING_FLOOR_CONFIRM_READS      2U        /* lectures consécutives "détecté" avant d'arrêter (anti-parasites) */
#define PARKING_SENSOR_FAIL_MAX          3U        /* erreurs I2C consécutives tolérées en déplacement */

/* --- Plateau : emplacements --- */
#define PARKING_SPACE_COUNT              7U        /* emplacements utilisés */
#define PARKING_SECTOR_COUNT             8U        /* secteurs de 45 degrés (7 emplacements + 1 vide) */

/* ====================================================================== */

typedef enum
{
    PARKING_HIGH_OK = 0,
    PARKING_HIGH_ERR_INIT,      /* ClickBoard / capteurs introuvables */
    PARKING_HIGH_ERR_SENSOR,    /* lecture des capteurs impossible (I2C) en déplacement */
    PARKING_HIGH_ERR_TIMEOUT,   /* étage non atteint dans PARKING_HEIGHT_TIMEOUT_MS */
    PARKING_HIGH_ERR_MOTOR      /* démarrage d'un moteur impossible */
} ParkingHigh_Error_t;

/* Initialise le ClickBoard (I2C), les capteurs d'étage et la logique. Ne bouge aucun moteur. */
HAL_StatusTypeDef ParkingHigh_Init(I2C_HandleTypeDef *hi2c);

/* À appeler le plus souvent possible (boucle principale). Non bloquant. */
void ParkingHigh_Process(void);

/* Étage atteint ou visé : 1 à 3 (0 = pas encore arrivé au premier étage). */
uint8_t ParkingHigh_GetFloor(void);

/* Emplacement du plateau : 1 à 7 (emplacement visé pendant une rotation). */
uint8_t ParkingHigh_GetSpace(void);

/* PARKING_HIGH_OK, sinon la cause de l'arrêt (les deux moteurs sont alors arrêtés). */
ParkingHigh_Error_t ParkingHigh_GetError(void);

/* ======================================================================
 * COMMANDES (points d'entrée) : à appeler pour demander un mouvement.
 * Pour l'instant personne ne les appelle ; plus tard, le CAN (réception de la commande + réponse ACK)
 * s'y branchera sans rien changer ici. LA LOGIQUE MOTEUR EST À ÉCRIRE : les corps sont vides, voir les TODO
 * dans parking_high.c.
 * Retour : HAL_OK = commande acceptée (le mouvement continue ensuite dans ParkingHigh_Process),
 *          HAL_ERROR = refusée (occupé, case invalide, erreur...).
 * ====================================================================== */
HAL_StatusTypeDef ParkingHigh_Home(void);                   /* initialisation des axes (fins de course) */
HAL_StatusTypeDef ParkingHigh_Store(uint8_t space);         /* ranger un véhicule dans la case 1 à 14 */
HAL_StatusTypeDef ParkingHigh_Retrieve(uint8_t space);      /* récupérer le véhicule de la case 1 à 14 */

/* 1 pendant un déplacement, 0 sinon (sera repris plus tard dans l'état envoyé par le CAN). */
uint8_t ParkingHigh_IsBusy(void);

#endif /* INC_PARKING_HIGH_H_ */
