/*
 * temp_test.c
 *
 * *** FICHIER TEMPORAIRE : a supprimer quand tout fonctionne ***
 *
 * Sortie par printf -> port COM (CN5). Rien n'est envoye tant que le moniteur serie n'est pas ouvert.
 *
 * Pour enlever le test :
 *   1. supprimer temp_test.c et temp_test.h
 *   2. dans main.c, supprimer les 2 lignes marquees "TEMP-TEST"
 *      (le #include et TempTest_Floor)
 */

#include "temp_test.h"
#include <stdio.h>
#include "usbd_cdc_if.h"

/* Une ligne est affichee a chaque passage, mais au plus toutes les 500 ms
 * (et tout de suite si un capteur change). */
#define PRINT_PERIOD_MS   500U

static const char *label(uint8_t state)
{
    /* state : 0 = rien, 1 = metal detecte, 2 = erreur de lecture I2C */
    return (state == 2U) ? "ERREUR I2C" : ((state == 1U) ? "METAL detecte" : "rien");
}

void TempTest_Floor(InductiveSensor_HandleTypeDef *dev)
{
    static uint8_t  prev[INDUCTIVE_SENSOR_COUNT];
    static uint8_t  was_open = 0U;
    static uint32_t last_print = 0U;
    uint8_t state[INDUCTIVE_SENSOR_COUNT];
    uint8_t changed = 0U;

    for (uint8_t i = 0U; i < INDUCTIVE_SENSOR_COUNT; i++)
    {
        uint8_t active;
        state[i] = (InductiveSensor_Read(dev, i, &active) == HAL_OK) ? active : 2U;

        if (state[i] != prev[i])
        {
            changed = 1U;
        }
        prev[i] = state[i];
    }

    uint8_t is_open = CDC_IsPortOpen();

    if (is_open != 0U)
    {
        uint32_t now = HAL_GetTick();

        if ((was_open == 0U) || (changed != 0U) || ((now - last_print) >= PRINT_PERIOD_MS))
        {
            printf("Capteur 1 : %s | Capteur 2 : %s | Capteur 3 : %s\r\n",
                   label(state[0]), label(state[1]), label(state[2]));
            last_print = now;
        }
    }

    was_open = is_open;
}
