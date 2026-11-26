/*
 * esa_can.c
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald
 *
 * Voir esa_can.h. Inspiré de la file circulaire de can_borne.c (Edwin).
 */

#include "esa_can.h"
#include <string.h>

static CAN_HandleTypeDef *s_hcan = NULL;
static bool s_loopback = false;
static bool s_echo_local = false;

/* File circulaire : l'interruption écrit à s_tete, la boucle principale lit à s_queue. */
static TrameCan          s_file[CAN_ESA_TAILLE_FILE_RX];
static volatile uint8_t  s_tete  = 0u;
static volatile uint8_t  s_queue = 0u;

static volatile CanEsa_Stats s_stats;
static uint32_t s_debut_blocage_tx = 0u;   /* 0 = boîtes non bloquées */

/* Ajoute une trame à la file (appelée en interruption, ou avec les interruptions masquées). */
static void empiler(uint16_t id, uint8_t dlc, const uint8_t *data8)
{
    uint8_t suivante = (uint8_t)((s_tete + 1u) % CAN_ESA_TAILLE_FILE_RX);
    if (suivante == s_queue)
    {
        s_stats.perdues_rx++;           /* file pleine : trame perdue */
        return;
    }
    s_file[s_tete].id  = id;
    s_file[s_tete].dlc = dlc;
    memcpy(s_file[s_tete].data, data8, 8);
    s_tete = suivante;
    s_stats.recues++;
}

bool CanEsa_Init(CAN_HandleTypeDef *hcan, bool loopback)
{
    CAN_FilterTypeDef filtre = { 0 };

    if (hcan == NULL)
    {
        return false;
    }
    s_hcan = hcan;
    s_loopback = loopback;

    if (loopback)
    {
        /* MX_CAN1_Init() a configuré le mode Normal : on réinitialise en loopback */
        hcan->Init.Mode = CAN_MODE_LOOPBACK;
        if (HAL_CAN_Init(hcan) != HAL_OK) { return false; }
    }

    /* Masque nul : toutes les trames vont dans la FIFO 0, le tri se fait dans le code */
    filtre.FilterBank           = 0;
    filtre.FilterMode           = CAN_FILTERMODE_IDMASK;
    filtre.FilterScale          = CAN_FILTERSCALE_32BIT;
    filtre.FilterIdHigh         = 0x0000;
    filtre.FilterIdLow          = 0x0000;
    filtre.FilterMaskIdHigh     = 0x0000;
    filtre.FilterMaskIdLow      = 0x0000;
    filtre.FilterFIFOAssignment = CAN_RX_FIFO0;
    filtre.FilterActivation     = ENABLE;
    filtre.SlaveStartFilterBank = 14;

    if (HAL_CAN_ConfigFilter(hcan, &filtre) != HAL_OK) { return false; }
    if (HAL_CAN_Start(hcan) != HAL_OK)                { return false; }
    if (HAL_CAN_ActivateNotification(hcan, CAN_IT_RX_FIFO0_MSG_PENDING) != HAL_OK)
    {
        return false;
    }
    return true;
}

bool CanEsa_Envoyer(uint16_t id, const uint8_t *data, uint8_t dlc)
{
    CAN_TxHeaderTypeDef entete = { 0 };
    uint8_t copie[8] = { 0 };
    uint32_t boite;

    if ((s_hcan == NULL) || (dlc > 8u) || (id > 0x7FFu))
    {
        return false;
    }
    if (HAL_CAN_GetTxMailboxesFreeLevel(s_hcan) == 0u)
    {
        s_stats.refusees_tx++;
        return false;
    }
    if ((data != NULL) && (dlc > 0u))
    {
        memcpy(copie, data, dlc);
    }
    entete.StdId = id;
    entete.IDE   = CAN_ID_STD;
    entete.RTR   = CAN_RTR_DATA;
    entete.DLC   = dlc;
    if (HAL_CAN_AddTxMessage(s_hcan, &entete, copie, &boite) != HAL_OK)
    {
        s_stats.refusees_tx++;
        return false;
    }
    s_stats.envoyees++;

    if (s_echo_local && !s_loopback)
    {
        uint32_t primask = __get_PRIMASK();
        __disable_irq();                 /* la file est aussi remplie par l'interruption CAN */
        empiler(id, dlc, copie);
        if (primask == 0u) { __enable_irq(); }
    }
    return true;
}

/* INTERRUPTION : on copie seulement les trames dans la file. */
void HAL_CAN_RxFifo0MsgPendingCallback(CAN_HandleTypeDef *hcan)
{
    CAN_RxHeaderTypeDef entete;
    uint8_t data[8];

    while (HAL_CAN_GetRxFifoFillLevel(hcan, CAN_RX_FIFO0) > 0u)
    {
        if (HAL_CAN_GetRxMessage(hcan, CAN_RX_FIFO0, &entete, data) != HAL_OK)
        {
            break;
        }
        if ((entete.IDE != CAN_ID_STD) || (entete.RTR != CAN_RTR_DATA))
        {
            continue;                       /* le protocole n'utilise que des trames de données standard */
        }
        empiler((uint16_t)entete.StdId, (uint8_t)entete.DLC, data);
    }
}

bool CanEsa_Recevoir(TrameCan *trame)
{
    if ((trame == NULL) || (s_queue == s_tete))
    {
        return false;
    }
    *trame  = s_file[s_queue];
    s_queue = (uint8_t)((s_queue + 1u) % CAN_ESA_TAILLE_FILE_RX);
    return true;
}

void CanEsa_Tache(uint32_t maintenant_ms)
{
    if (s_hcan == NULL)
    {
        return;
    }
    if (HAL_CAN_GetTxMailboxesFreeLevel(s_hcan) > 0u)
    {
        s_debut_blocage_tx = 0u;
        return;
    }
    /* Les 3 boîtes sont pleines : probablement aucun autre nœud pour accuser réception */
    if (s_debut_blocage_tx == 0u)
    {
        s_debut_blocage_tx = (maintenant_ms == 0u) ? 1u : maintenant_ms;
        return;
    }
    if ((maintenant_ms - s_debut_blocage_tx) >= CAN_ESA_DELAI_BLOCAGE_TX_MS)
    {
        HAL_CAN_AbortTxRequest(s_hcan, CAN_TX_MAILBOX0 | CAN_TX_MAILBOX1 | CAN_TX_MAILBOX2);
        s_stats.annulees_tx += 3u;
        s_debut_blocage_tx = 0u;
    }
}

CanEsa_Stats CanEsa_LireStats(void)
{
    CanEsa_Stats copie;
    __disable_irq();
    copie = s_stats;
    __enable_irq();
    return copie;
}

bool CanEsa_EnLoopback(void)
{
    return s_loopback;
}

void CanEsa_ActiverEchoLocal(bool actif)
{
    s_echo_local = actif;
}

bool CanEsa_EchoLocal(void)
{
    return s_echo_local;
}
