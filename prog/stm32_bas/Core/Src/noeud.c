/*
 * noeud.c
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald
 *
 * Voir noeud.h.
 */

#include "noeud.h"
#include "esa_can_ids.h"
#include "esa_noeud.h"
#include "t07_del.h"
#include "main.h"
#if (ESA_NOEUD == ESA_NOEUD_BAS)
#include "t06_ir.h"
#endif

#if (ESA_NOEUD == ESA_NOEUD_BAS)
#define ID_HEARTBEAT_NOEUD   CAN_ID_HEARTBEAT_BAS
#elif (ESA_NOEUD == ESA_NOEUD_HAUT)
#define ID_HEARTBEAT_NOEUD   CAN_ID_HEARTBEAT_HAUT
#elif (ESA_NOEUD == ESA_NOEUD_BORNE)
#define ID_HEARTBEAT_NOEUD   CAN_ID_HEARTBEAT_BORNE
#endif

static uint32_t          s_t_heartbeat;
static uint8_t           s_compteur_heartbeat;
static bool              s_rpi_en_ligne;
static uint32_t          s_t_dernier_hb_rpi;
static Noeud_Observateur s_observateur;

static void changer_etat_rpi(bool en_ligne)
{
    s_rpi_en_ligne = en_ligne;
    T07_SignalerRpi(en_ligne);
    HAL_GPIO_WritePin(LED_BLEUE_GPIO_Port, LED_BLEUE_Pin, en_ligne ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

void Noeud_Init(uint32_t maintenant_ms)
{
    s_t_heartbeat        = maintenant_ms;
    s_compteur_heartbeat = 0u;
    s_rpi_en_ligne       = false;
    s_t_dernier_hb_rpi   = maintenant_ms;
    s_observateur        = NULL;
}

void Noeud_DefinirObservateur(Noeud_Observateur observateur)
{
    s_observateur = observateur;
}

bool Noeud_RpiEnLigne(void)
{
    return s_rpi_en_ligne;
}

void Noeud_Tache(uint32_t maintenant_ms)
{
    TrameCan trame;

    /* 1. Trames reçues : surveillance du RPi, puis aiguillage vers les modules */
    while (CanEsa_Recevoir(&trame))
    {
        if (trame.id == CAN_ID_HEARTBEAT_RPI)
        {
            s_t_dernier_hb_rpi = maintenant_ms;
            if (!s_rpi_en_ligne)
            {
                changer_etat_rpi(true);
            }
        }

        T07_TraiterTrame(trame.id, trame.dlc, trame.data);
#if (ESA_NOEUD == ESA_NOEUD_BAS)
        T06_TraiterTrame(trame.id, trame.dlc, trame.data);   /* IR_LECTURE_CMD 0x302, SYNCHRO_CMD 0x080 */
#endif

        if (s_observateur != NULL)
        {
            s_observateur(&trame);
        }
    }

    /* 2. Perte du heartbeat du RPi */
    if (s_rpi_en_ligne && ((maintenant_ms - s_t_dernier_hb_rpi) >= NOEUD_DELAI_PERTE_RPI_MS))
    {
        changer_etat_rpi(false);
    }

    /* 3. Heartbeat du nœud : [compteur, état] toutes les 500 ms */
    if ((maintenant_ms - s_t_heartbeat) >= NOEUD_PERIODE_HEARTBEAT_MS)
    {
        uint8_t data[2] = { s_compteur_heartbeat, HEARTBEAT_ETAT_PRET };
        s_t_heartbeat += NOEUD_PERIODE_HEARTBEAT_MS;     /* période régulière, sans dérive */
        if ((maintenant_ms - s_t_heartbeat) >= NOEUD_PERIODE_HEARTBEAT_MS)
        {
            s_t_heartbeat = maintenant_ms;               /* retard important : on se recale */
        }
        CanEsa_Envoyer(ID_HEARTBEAT_NOEUD, data, sizeof data);
        s_compteur_heartbeat++;
        HAL_GPIO_TogglePin(LED_VERTE_GPIO_Port, LED_VERTE_Pin);
    }
}
