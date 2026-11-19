/*
 * temp_test.c
 *
 * *** FICHIER TEMPORAIRE : a supprimer quand tout fonctionne ***
 *
 * Tout sort par printf. Rien ne s'affiche tant qu'aucune sortie serie n'est branchee
 * (il faut definir __io_putchar ou _write ailleurs dans le projet).
 *
 * Pour enlever le test :
 *   1. supprimer temp_test.c et temp_test.h
 *   2. dans main.c, supprimer les lignes marquees "TEMP-TEST"
 *      (le #include, TempTest_ClickBoard, TempTest_Floor et les 2 printf "Rotation")
 */

#include "temp_test.h"

#define TEMP_REPORT_PERIOD_MS   3000U   /* le rapport est reaffiche toutes les 3 s */

static uint8_t           scan_addr[16];
static uint8_t           scan_count;
static uint8_t           addr_expected;
static HAL_StatusTypeDef clickboard_init_status;

static void print_report(void)
{
    uint8_t found_expected = 0U;
    uint8_t found_20 = 0U;
    uint8_t found_21 = 0U;

    printf("\r\n=== TEST TEMPORAIRE ClickBoard ===\r\n");
    printf("Adresse TCA6416A dans tca6416a.h : 0x%02X\r\n", (unsigned)addr_expected);
    printf("Scan I2C1, appareils qui repondent :");

    if (scan_count == 0U)
    {
        printf(" aucun");
    }

    for (uint8_t i = 0U; (i < scan_count) && (i < (uint8_t)sizeof(scan_addr)); i++)
    {
        printf(" 0x%02X", (unsigned)scan_addr[i]);
        if (scan_addr[i] == addr_expected) { found_expected = 1U; }
        if (scan_addr[i] == 0x20U)         { found_20 = 1U; }
        if (scan_addr[i] == 0x21U)         { found_21 = 1U; }
    }
    printf("\r\n");

    if (scan_count == 0U)
    {
        printf("-> AUCUN appareil : ClickBoard absent, pas alimente, ou SDA/SCL a verifier\r\n");
    }
    else if (found_expected != 0U)
    {
        printf("-> OK : le TCA6416A repond a l'adresse configuree\r\n");
    }
    else if ((found_20 != 0U) || (found_21 != 0U))
    {
        printf("-> MAUVAISE ADRESSE : mets TCA6416A_ADDR_PWM a (0x%02XU << 1) dans tca6416a.h\r\n",
               (unsigned)((found_20 != 0U) ? 0x20U : 0x21U));
    }
    else
    {
        printf("-> Des appareils repondent mais pas a 0x20 ni 0x21 : verifier S1C et la carte\r\n");
    }

    printf("ClickBoard_InitPWM : %s\r\n", (clickboard_init_status == HAL_OK) ? "OK" : "ECHEC");
}

void TempTest_ClickBoard(I2C_HandleTypeDef *hi2c, HAL_StatusTypeDef init_status)
{
    addr_expected = (uint8_t)(TCA6416A_ADDR_PWM >> 1);
    clickboard_init_status = init_status;
    scan_count = 0U;

    for (uint8_t addr = 0x08U; addr < 0x78U; addr++)
    {
        if (HAL_I2C_IsDeviceReady(hi2c, (uint16_t)(addr << 1), 1U, 10U) == HAL_OK)
        {
            if (scan_count < (uint8_t)sizeof(scan_addr))
            {
                scan_addr[scan_count] = addr;
            }
            scan_count++;
        }
    }

    print_report();
}

void TempTest_Floor(InductiveSensor_HandleTypeDef *dev)
{
    static uint8_t  prev[INDUCTIVE_SENSOR_COUNT] = { 0xFFU, 0xFFU, 0xFFU };  /* 0xFF = pas encore affiche */
    static uint32_t next_report_ms = 0U;
    uint8_t state[INDUCTIVE_SENSOR_COUNT];

    for (uint8_t i = 0U; i < INDUCTIVE_SENSOR_COUNT; i++)
    {
        uint8_t active;

        /* 0 = rien, 1 = metal detecte, 2 = erreur de lecture I2C */
        state[i] = (InductiveSensor_Read(dev, i, &active) == HAL_OK) ? active : 2U;

        if (state[i] != prev[i])
        {
            prev[i] = state[i];
            printf("Capteur %u : %s\r\n", (unsigned)(i + 1U),
                   (state[i] == 2U) ? "ERREUR lecture I2C" : ((state[i] == 1U) ? "METAL detecte" : "rien"));
        }
    }

    if (HAL_GetTick() >= next_report_ms)
    {
        next_report_ms = HAL_GetTick() + TEMP_REPORT_PERIOD_MS;
        print_report();
        printf("Capteurs : 1=%u 2=%u 3=%u  (0 = rien, 1 = metal, 2 = erreur)\r\n",
               (unsigned)state[0], (unsigned)state[1], (unsigned)state[2]);
    }
}
