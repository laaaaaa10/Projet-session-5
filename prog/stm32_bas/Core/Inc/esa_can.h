/*
 * esa_can.h
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald
 *
 * Service CAN du STM32 BAS (réutilisable sur les autres nœuds).
 *
 * - Toutes les trames standard sont acceptées dans la FIFO 0 ; l'interruption
 *   les copie dans une file circulaire, la boucle principale les lit avec
 *   CanEsa_Recevoir() (aucun traitement en interruption).
 * - CanEsa_Envoyer() place une trame dans une boîte d'émission libre.
 * - La retransmission automatique est activée (CubeMX) : sans autre nœud pour
 *   accuser réception, une trame serait renvoyée sans fin et occuperait une
 *   boîte. CanEsa_Tache() annule les envois bloqués trop longtemps.
 * - Mode loopback (essai sur la Discovery seule, sans transceiver) : le
 *   contrôleur reçoit ses propres trames ; l'accusé de réception est ignoré.
 */

#ifndef INC_ESA_CAN_H_
#define INC_ESA_CAN_H_

#include <stdbool.h>
#include <stdint.h>
#include "stm32f4xx_hal.h"   /* CAN_HandleTypeDef */

#define CAN_ESA_TAILLE_FILE_RX       32u    /* trames en attente de lecture */
#define CAN_ESA_DELAI_BLOCAGE_TX_MS  100u   /* boîtes pleines plus longtemps : envois annulés */

typedef struct
{
    uint16_t id;
    uint8_t  dlc;
    uint8_t  data[8];
} TrameCan;

typedef struct
{
    uint32_t recues;          /* trames placées dans la file */
    uint32_t perdues_rx;      /* file pleine */
    uint32_t envoyees;        /* trames confiées à une boîte d'émission */
    uint32_t refusees_tx;     /* aucune boîte libre au moment de l'envoi */
    uint32_t annulees_tx;     /* envois annulés car bloqués (pas d'accusé de réception) */
} CanEsa_Stats;

/* Configure le filtre, démarre le CAN et active l'interruption de réception.
 * loopback = true : mode boucle interne pour les essais sans bus. */
bool CanEsa_Init(CAN_HandleTypeDef *hcan, bool loopback);

/* Envoie une trame de données standard. false si DLC > 8 ou aucune boîte libre. */
bool CanEsa_Envoyer(uint16_t id, const uint8_t *data, uint8_t dlc);

/* Retire la trame la plus ancienne de la file. false si la file est vide. */
bool CanEsa_Recevoir(TrameCan *trame);

/* À appeler dans la boucle principale : surveille les boîtes d'émission bloquées. */
void CanEsa_Tache(uint32_t maintenant_ms);

/* Compteurs de diagnostic. */
CanEsa_Stats CanEsa_LireStats(void);

/* true si le CAN tourne en loopback. */
bool CanEsa_EnLoopback(void);

#endif /* INC_ESA_CAN_H_ */
