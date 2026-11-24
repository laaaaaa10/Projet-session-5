/**
 * @file    can_borne.h
 * @brief   Service CAN du STM32 Borne (partageable avec T01 / T07).
 *
 * Un seul module initialise CAN1. Les trames reçues sont copiées en
 * interruption dans une file circulaire, puis lues dans la boucle principale.
 *
 * Projet ESA - 243-557 - Automne 2026
 */
#ifndef CAN_BORNE_H
#define CAN_BORNE_H

#include <stdbool.h>
#include <stdint.h>
#include "main.h"          /* CAN_HandleTypeDef */

/* Une trame CAN standard (identifiant 11 bits, 0 à 8 octets de données) */
typedef struct
{
    uint16_t id;
    uint8_t  dlc;
    uint8_t  data[8];
} TrameCan;

/* Configure le filtre, démarre CAN1 et active l'interruption de réception */
bool CanBorne_Init(CAN_HandleTypeDef *hcan);

/* Envoie une trame de données standard ; false si les 3 boîtes d'émission sont pleines */
bool CanBorne_Envoyer(uint16_t id, const uint8_t *data, uint8_t dlc);

/* Retire la trame la plus ancienne de la file ; false si la file est vide */
bool CanBorne_Recevoir(TrameCan *trame);

#endif /* CAN_BORNE_H */
