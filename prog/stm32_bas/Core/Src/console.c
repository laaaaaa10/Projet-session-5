/*
 * console.c
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald
 *
 * Voir console.h.
 */

#include "console.h"
#include "main.h"
#include "usart.h"
#include "usb_device.h"
#include "usbd_cdc.h"
#include "usbd_cdc_if.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#define CONSOLE_TAILLE_FILE     2048u  /* octets en attente par sortie */
#define CONSOLE_TAILLE_PRINTF   128u
#define CONSOLE_TAILLE_ENTREE   128u   /* caractères reçus pas encore lus */
#define CONSOLE_TAILLE_LIGNE    80u

extern USBD_HandleTypeDef hUsbDeviceFS;   /* défini dans usb_device.c (CubeMX) */

/* ======================= Sortie ======================= */

/* Une sortie : le texte en attente, et la copie lue pendant l'envoi (USB ou interruption UART). */
typedef struct
{
    uint8_t  attente[CONSOLE_TAILLE_FILE];
    uint16_t nb_attente;
    uint8_t  envoi[CONSOLE_TAILLE_FILE];
} Sortie;

static Sortie sortie_usb;
static Sortie sortie_uart;

static void ajouter(Sortie *s, const char *texte, uint16_t longueur)
{
    if (longueur > CONSOLE_TAILLE_FILE)
    {
        longueur = CONSOLE_TAILLE_FILE;
    }
    /* File pleine (aucun terminal ouvert) : on abandonne les vieux messages */
    if (longueur > (uint16_t)(CONSOLE_TAILLE_FILE - s->nb_attente))
    {
        s->nb_attente = 0u;
    }
    memcpy(&s->attente[s->nb_attente], texte, longueur);
    s->nb_attente = (uint16_t)(s->nb_attente + longueur);
}

static void envoyer_usb(void)
{
    if (sortie_usb.nb_attente == 0u)
    {
        return;
    }
    /* Le PC n'a pas encore configuré le port : CDC_Transmit_FS planterait (pClassData nul) */
    if ((hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) || (hUsbDeviceFS.pClassData == NULL))
    {
        return;
    }
    USBD_CDC_HandleTypeDef *hcdc = (USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;
    if (hcdc->TxState != 0u)
    {
        return;                                   /* envoi précédent en cours */
    }
    memcpy(sortie_usb.envoi, sortie_usb.attente, sortie_usb.nb_attente);
    if (CDC_Transmit_FS(sortie_usb.envoi, sortie_usb.nb_attente) == USBD_OK)
    {
        sortie_usb.nb_attente = 0u;
    }
}

static void envoyer_uart(void)
{
    if ((sortie_uart.nb_attente == 0u) || (huart2.gState != HAL_UART_STATE_READY))
    {
        return;
    }
    memcpy(sortie_uart.envoi, sortie_uart.attente, sortie_uart.nb_attente);
    if (HAL_UART_Transmit_IT(&huart2, sortie_uart.envoi, sortie_uart.nb_attente) == HAL_OK)
    {
        sortie_uart.nb_attente = 0u;
    }
}

void Console_Ecrire(const char *texte)
{
    uint16_t longueur = (uint16_t)strlen(texte);
    ajouter(&sortie_usb, texte, longueur);
    ajouter(&sortie_uart, texte, longueur);
    Console_Tache();
}

void Console_Printf(const char *format, ...)
{
    char texte[CONSOLE_TAILLE_PRINTF];
    va_list args;
    va_start(args, format);
    vsnprintf(texte, sizeof texte, format, args);
    va_end(args);
    Console_Ecrire(texte);
}

void Console_Tache(void)
{
    envoyer_usb();
    envoyer_uart();
}

/* ======================= Entrée ======================= */

static volatile uint8_t  s_entree[CONSOLE_TAILLE_ENTREE];
static volatile uint16_t s_entree_tete  = 0u;   /* écrit en interruption */
static volatile uint16_t s_entree_queue = 0u;   /* lu dans la boucle principale */
static uint8_t           s_octet_uart;
static char              s_ligne[CONSOLE_TAILLE_LIGNE];
static uint16_t          s_longueur_ligne = 0u;

void Console_RecevoirOctets(const uint8_t *data, uint32_t longueur)
{
    for (uint32_t i = 0u; i < longueur; i++)
    {
        uint16_t suivante = (uint16_t)((s_entree_tete + 1u) % CONSOLE_TAILLE_ENTREE);
        if (suivante == s_entree_queue)
        {
            return;                      /* file pleine : le reste est perdu */
        }
        s_entree[s_entree_tete] = data[i];
        s_entree_tete = suivante;
    }
}

void Console_Init(void)
{
    HAL_UART_Receive_IT(&huart2, &s_octet_uart, 1u);
}

/* INTERRUPTION : un octet reçu sur l'USART2 */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart == &huart2)
    {
        Console_RecevoirOctets(&s_octet_uart, 1u);
        HAL_UART_Receive_IT(&huart2, &s_octet_uart, 1u);
    }
}

/* INTERRUPTION : erreur UART (débordement, bruit) : on relance la réception */
void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (huart == &huart2)
    {
        HAL_UART_Receive_IT(&huart2, &s_octet_uart, 1u);
    }
}

bool Console_LireLigne(char *ligne, uint16_t taille)
{
    while (s_entree_queue != s_entree_tete)
    {
        char c = (char)s_entree[s_entree_queue];
        s_entree_queue = (uint16_t)((s_entree_queue + 1u) % CONSOLE_TAILLE_ENTREE);

        if ((c == '\r') || (c == '\n'))
        {
            if (s_longueur_ligne == 0u)
            {
                continue;                /* ligne vide ou \n après \r */
            }
            Console_Ecrire("\r\n");
            s_ligne[s_longueur_ligne] = '\0';
            strncpy(ligne, s_ligne, taille - 1u);
            ligne[taille - 1u] = '\0';
            s_longueur_ligne = 0u;
            return true;
        }
        if ((c == '\b') || (c == 0x7F))  /* retour arrière */
        {
            if (s_longueur_ligne > 0u)
            {
                s_longueur_ligne--;
                Console_Ecrire("\b \b");
            }
            continue;
        }
        if ((c >= ' ') && (c <= '~') && (s_longueur_ligne < (CONSOLE_TAILLE_LIGNE - 1u)))
        {
            char echo[2] = { c, '\0' };
            s_ligne[s_longueur_ligne++] = c;
            Console_Ecrire(echo);
        }
    }
    return false;
}
