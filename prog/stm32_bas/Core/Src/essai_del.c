/*
 * essai_del.c
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald (T07)
 *
 * Voir essai_del.h.
 */

#include "essai_del.h"
#include "main.h"
#include "spi.h"
#include "console.h"
#include "rgb_led_chain.h"

/* ---- Paramètres de l'essai ---- */
#define ESSAI_NB_DEL            15u     /* chaîne du PCB-03 : D9 (indice 0) à D23 (indice 14) */
#define ESSAI_LUMINOSITE        8u      /* luminosité globale 0 à 31 : faible pour limiter le courant */
#define ESSAI_DUREE_COULEUR_MS  400u    /* durée de chaque couleur */
#define ESSAI_PERIODE_VIE_MS    500u    /* clignotement de la DEL verte de la Discovery */
#define ESSAI_ANTIREBOND_MS     200u    /* bouton bleu */

typedef struct
{
    uint8_t rouge, vert, bleu;
    const char *nom;
} Couleur;

static const Couleur couleurs[] =
{
    { 255u,   0u,   0u, "rouge" },
    {   0u, 255u,   0u, "vert"  },
    {   0u,   0u, 255u, "bleu"  },
    { 255u, 255u, 255u, "blanc" },
};
#define NB_COULEURS  (sizeof(couleurs) / sizeof(couleurs[0]))

static RgbLedChain_HandleTypeDef chaine;   /* globale : lue par le DMA après Show() */

static uint8_t  del_courante;
static uint8_t  couleur_courante;
static uint8_t  en_pause;
static uint8_t  envoi_en_attente;          /* Show() a répondu HAL_BUSY : réessayer */
static uint8_t  bouton_precedent;
static uint32_t t_couleur;
static uint32_t t_vie;
static uint32_t t_bouton;

static void envoyer_image(void)
{
    envoi_en_attente = (RgbLedChain_Show(&chaine) == HAL_BUSY) ? 1u : 0u;
}

static void afficher_etape(void)
{
    const Couleur *c = &couleurs[couleur_courante];

    RgbLedChain_Clear(&chaine);
    RgbLedChain_SetColor(&chaine, del_courante, c->rouge, c->vert, c->bleu, ESSAI_LUMINOSITE);
    envoyer_image();

    Console_Printf("DEL indice %2u (D%u) : %s\r\n",
                   (unsigned)del_courante, (unsigned)(9u + del_courante), c->nom);
}

static void etape_suivante(void)
{
    couleur_courante++;
    if (couleur_courante >= NB_COULEURS)
    {
        couleur_courante = 0u;
        del_courante = (uint8_t)((del_courante + 1u) % ESSAI_NB_DEL);
        if (del_courante == 0u)
        {
            Console_Ecrire("---- tour complet ----\r\n");
        }
    }
    afficher_etape();
}

void EssaiDel_Init(void)
{
    /* OE du translateur du PCB-11 : doit rester haut pendant l'envoi */
    HAL_GPIO_WritePin(LED_OE_GPIO_Port, LED_OE_Pin, GPIO_PIN_SET);

    Console_Ecrire("\r\n=== Essai DEL T07 (STM32 BAS) ===\r\n");
    Console_Ecrire("Une DEL a la fois : rouge, vert, bleu, blanc. Bouton bleu = pause.\r\n");

    if (RgbLedChain_Init(&chaine, &hspi1, ESSAI_NB_DEL) != HAL_OK)
    {
        Console_Ecrire("ERREUR : RgbLedChain_Init\r\n");
        return;
    }
    envoyer_image();                        /* toutes éteintes */

    del_courante     = 0u;
    couleur_courante = 0u;
    en_pause         = 0u;
    t_couleur = t_vie = t_bouton = HAL_GetTick();
    afficher_etape();
}

void EssaiDel_Tache(void)
{
    uint32_t maintenant = HAL_GetTick();

    /* Indicateur de vie */
    if ((maintenant - t_vie) >= ESSAI_PERIODE_VIE_MS)
    {
        t_vie = maintenant;
        HAL_GPIO_TogglePin(LED_VERTE_GPIO_Port, LED_VERTE_Pin);
    }

    /* Bouton bleu (actif haut) : pause / reprise sur front montant */
    uint8_t bouton = (HAL_GPIO_ReadPin(BTN_USER_GPIO_Port, BTN_USER_Pin) == GPIO_PIN_SET) ? 1u : 0u;
    if ((bouton != 0u) && (bouton_precedent == 0u) && ((maintenant - t_bouton) >= ESSAI_ANTIREBOND_MS))
    {
        t_bouton = maintenant;
        en_pause = (uint8_t)!en_pause;
        Console_Ecrire(en_pause ? "Pause\r\n" : "Reprise\r\n");
        t_couleur = maintenant;
    }
    bouton_precedent = bouton;

    /* Envoi refusé plus tôt parce que le DMA était occupé */
    if (envoi_en_attente != 0u)
    {
        envoyer_image();
    }

    /* Couleur suivante */
    if ((en_pause == 0u) && ((maintenant - t_couleur) >= ESSAI_DUREE_COULEUR_MS))
    {
        t_couleur = maintenant;
        etape_suivante();
    }
}
