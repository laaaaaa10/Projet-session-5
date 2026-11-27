/*
 * t06_pcb04.c
 *
 *  Created on: 25 nov. 2026
 *      Author: William MacDonald (T06)
 *
 * Voir t06_pcb04.h.
 *
 * Bus I2C bloqué : si le STM32 est réinitialisé (RESET, flash) au milieu d'une
 * lecture, le TCA6416A, qui reste alimenté, peut garder SDA à 0 en attendant des
 * coups d'horloge. Le STM32 voit alors le bus « occupé » et toute transaction
 * échoue. Avant chaque (ré)initialisation, on libère donc le bus : jusqu'à 9
 * impulsions sur SCL en GPIO, une condition STOP, puis une remise à zéro du
 * périphérique I2C. Après plusieurs échecs de suite, la carte est réinitialisée
 * automatiquement (au plus une tentative par seconde).
 */

#include "t06_pcb04.h"

#define ECHECS_AVANT_REPRISE    3u      /* échecs I2C consécutifs avant de réinitialiser la carte */
#define DELAI_ENTRE_ESSAIS_MS   1000u   /* entre deux tentatives d'initialisation */
#define IMPULSIONS_DEBLOCAGE    9u

/* Broches I2C des MikroBus du PCB-12 (voir i2c.c généré par CubeMX) */
typedef struct
{
    GPIO_TypeDef *port_scl;
    uint16_t      broche_scl;
    GPIO_TypeDef *port_sda;
    uint16_t      broche_sda;
} BrochesI2c;

static bool broches_du_bus(const I2C_HandleTypeDef *hi2c, BrochesI2c *b)
{
    if (hi2c->Instance == I2C3)          /* MikroBus 1 : SCL PA8, SDA PC9 */
    {
        b->port_scl = GPIOA; b->broche_scl = GPIO_PIN_8;
        b->port_sda = GPIOC; b->broche_sda = GPIO_PIN_9;
        return true;
    }
    if (hi2c->Instance == I2C1)          /* MikroBus 2 : SCL PB6, SDA PB9 */
    {
        b->port_scl = GPIOB; b->broche_scl = GPIO_PIN_6;
        b->port_sda = GPIOB; b->broche_sda = GPIO_PIN_9;
        return true;
    }
    return false;
}

static void reinitialiser_peripherique(I2C_HandleTypeDef *hi2c)
{
    if (hi2c->Instance == I2C3)
    {
        __HAL_RCC_I2C3_FORCE_RESET();
        __HAL_RCC_I2C3_RELEASE_RESET();
    }
    else if (hi2c->Instance == I2C1)
    {
        __HAL_RCC_I2C1_FORCE_RESET();
        __HAL_RCC_I2C1_RELEASE_RESET();
    }
}

/* Libère un esclave qui tient SDA à 0, puis réinitialise le périphérique I2C. */
static void debloquer_bus(I2C_HandleTypeDef *hi2c)
{
    BrochesI2c b;
    if (!broches_du_bus(hi2c, &b))
    {
        return;
    }

    (void)HAL_I2C_DeInit(hi2c);                         /* rend les broches au GPIO */

    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();

    GPIO_InitTypeDef gpio = { 0 };
    gpio.Mode  = GPIO_MODE_OUTPUT_OD;                    /* pull-ups de la PCB-04 */
    gpio.Pull  = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_WritePin(b.port_scl, b.broche_scl, GPIO_PIN_SET);
    HAL_GPIO_WritePin(b.port_sda, b.broche_sda, GPIO_PIN_SET);
    gpio.Pin = b.broche_scl; HAL_GPIO_Init(b.port_scl, &gpio);
    gpio.Pin = b.broche_sda; HAL_GPIO_Init(b.port_sda, &gpio);
    HAL_Delay(1);

    /* Horloge jusqu'à ce que l'esclave relâche SDA (au plus 9 bits) */
    for (uint8_t i = 0u; (i < IMPULSIONS_DEBLOCAGE) &&
                         (HAL_GPIO_ReadPin(b.port_sda, b.broche_sda) == GPIO_PIN_RESET); i++)
    {
        HAL_GPIO_WritePin(b.port_scl, b.broche_scl, GPIO_PIN_RESET);
        HAL_Delay(1);
        HAL_GPIO_WritePin(b.port_scl, b.broche_scl, GPIO_PIN_SET);
        HAL_Delay(1);
    }

    /* Condition STOP : SDA monte pendant que SCL est haut */
    HAL_GPIO_WritePin(b.port_scl, b.broche_scl, GPIO_PIN_RESET);
    HAL_Delay(1);
    HAL_GPIO_WritePin(b.port_sda, b.broche_sda, GPIO_PIN_RESET);
    HAL_Delay(1);
    HAL_GPIO_WritePin(b.port_scl, b.broche_scl, GPIO_PIN_SET);
    HAL_Delay(1);
    HAL_GPIO_WritePin(b.port_sda, b.broche_sda, GPIO_PIN_SET);
    HAL_Delay(1);

    reinitialiser_peripherique(hi2c);                    /* efface aussi un drapeau BUSY figé */
    (void)HAL_I2C_Init(hi2c);                            /* remet les broches en mode I2C */
}

/* Déblocage du bus, puis configuration de la carte ; démarre le PWM une seule fois. */
static bool initialiser(T06_Pcb04 *carte)
{
    debloquer_bus(carte->hi2c);

    /* TCA6416A à 0x20, TMUX1308 désactivé, P1.0-P1.3 en sorties */
    if (ClickBoard_InitPWM(&carte->cb, carte->hi2c) != HAL_OK)
    {
        return false;
    }
    /* P0.0-P0.7 : entrées (valeur par défaut du TCA6416A, réimposée au cas où) */
    for (uint8_t broche = 0u; broche < 8u; broche++)
    {
        if (TCA6416A_PinMode(&carte->cb.tca, broche, TCA6416A_INPUT) != HAL_OK)
        {
            return false;
        }
    }
    /* Porteuse 38 kHz, 50 % (période et impulsion réglées dans CubeMX) */
    if (!carte->pwm_demarre)
    {
        if (HAL_TIM_PWM_Start(carte->htim, carte->canal_tim) != HAL_OK)
        {
            return false;
        }
        carte->pwm_demarre = true;
    }
    return true;
}

/* Carte hors service : nouvelle tentative au plus une fois par seconde. */
static bool disponible(T06_Pcb04 *carte)
{
    if (carte->pret)
    {
        return true;
    }
    uint32_t maintenant = HAL_GetTick();
    if ((int32_t)(maintenant - carte->t_prochain_essai) < 0)
    {
        return false;
    }
    carte->pret = initialiser(carte);
    carte->echecs_consecutifs = 0u;
    if (carte->pret)
    {
        carte->reprises++;
    }
    else
    {
        carte->t_prochain_essai = HAL_GetTick() + DELAI_ENTRE_ESSAIS_MS;
    }
    return carte->pret;
}

static bool noter(T06_Pcb04 *carte, HAL_StatusTypeDef st)
{
    if (st == HAL_OK)
    {
        carte->echecs_consecutifs = 0u;
        return true;
    }
    carte->echecs_consecutifs++;
    if (carte->echecs_consecutifs >= ECHECS_AVANT_REPRISE)
    {
        carte->pret = false;                              /* réinitialisation au prochain appel */
        carte->t_prochain_essai = HAL_GetTick();
    }
    return false;
}

static bool choisir_emetteur(void *ctx, int8_t circuit)
{
    T06_Pcb04 *carte = (T06_Pcb04 *)ctx;

    if (!disponible(carte))
    {
        return false;
    }
    if (circuit < 0)
    {
        return noter(carte, ClickBoard_DisableMux(&carte->cb));       /* EN_B = 1 : aucun émetteur */
    }
    return noter(carte, ClickBoard_SelectChannel(&carte->cb, (uint8_t)circuit));
}

static bool lire_recepteurs(void *ctx, uint8_t *niveaux)
{
    T06_Pcb04 *carte = (T06_Pcb04 *)ctx;

    if (!disponible(carte))
    {
        return false;
    }
    return noter(carte, TCA6416A_ReadPort(&carte->cb.tca, 0u, niveaux));
}

bool T06_Pcb04_Init(T06_Pcb04 *carte, I2C_HandleTypeDef *hi2c, TIM_HandleTypeDef *htim, uint32_t canal_tim)
{
    if ((carte == NULL) || (hi2c == NULL) || (htim == NULL))
    {
        return false;
    }
    carte->hi2c = hi2c;
    carte->htim = htim;
    carte->canal_tim = canal_tim;
    carte->pwm_demarre = false;
    carte->echecs_consecutifs = 0u;
    carte->reprises = 0u;
    carte->pret = initialiser(carte);
    carte->t_prochain_essai = HAL_GetTick() + DELAI_ENTRE_ESSAIS_MS;
    return carte->pret;
}

T06_Carte T06_Pcb04_Interface(T06_Pcb04 *carte)
{
    T06_Carte interface = { choisir_emetteur, lire_recepteurs, carte };
    return interface;
}
