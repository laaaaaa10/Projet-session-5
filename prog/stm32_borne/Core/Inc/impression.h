/**
 * @file    impression.h
 * @brief   T05 - Impression des billets (STM32 Borne).
 *
 * Reçoit IMPRESSION_CMD (0x360) et IMPRESSION_DATE (0x361), les apparie
 * par numéro de séquence, valide les champs, compose le billet, l'envoie
 * à l'imprimante par UART (interruption) et répond au RPi avec
 * IMPRESSION_ETAT (0x230). Protocole CAN ESA v1.6, section 9.
 *
 * Projet ESA - 243-557 - Automne 2026
 * Auteur : Edwin (T05)
 */
#ifndef IMPRESSION_H
#define IMPRESSION_H

#include <stdbool.h>
#include <stdint.h>
#include "escpos.h"

/* --- Identifiants CAN (protocole v1.6) ----------------------------------- */
#define CAN_ID_IMPRESSION_ETAT   0x230u   /* Borne → RPi */
#define CAN_ID_IMPRESSION_CMD    0x360u   /* RPi → Borne */
#define CAN_ID_IMPRESSION_DATE   0x361u   /* RPi → Borne */

/* --- DB1 de 0x230 : résultat --------------------------------------------- */
#define IMPR_RES_REFUSEE         0u   /* données invalides ou imprimante occupée */
#define IMPR_RES_VALIDEES        1u   /* paire complète et valide, envoi lancé   */
#define IMPR_RES_ENVOYEE_UART    2u   /* octets envoyés (≠ papier sorti)         */
#define IMPR_RES_ERREUR          3u   /* délai dépassé, erreur UART...           */

/* --- DB2 de 0x230 : codes d'erreur propres à T05 ------------------------- */
#define IMPR_ERR_AUCUNE          0x00u
#define IMPR_ERR_DLC             0x01u   /* DLC ≠ 8 (0x360) ou ≠ 7 (0x361)        */
#define IMPR_ERR_TYPE            0x02u   /* DB1 de 0x360 ≠ 0x01                   */
#define IMPR_ERR_TRANSACTION     0x03u   /* numéro > 999 999                      */
#define IMPR_ERR_PLACE           0x04u   /* place hors 1-14                       */
#define IMPR_ERR_DATE            0x05u   /* date ou heure impossible              */
#define IMPR_ERR_TRAME_MANQUANTE 0x06u   /* trame complémentaire absente          */
#define IMPR_ERR_OCCUPEE         0x07u   /* une impression est déjà en cours      */
#define IMPR_ERR_UART            0x08u   /* erreur HAL au démarrage ou pendant    */
#define IMPR_ERR_DELAI_UART      0x09u   /* envoi UART non terminé à temps        */
#define IMPR_ERR_INCOHERENCE     0x0Bu   /* même séquence, contenu différent      */

/* --- Données d'un billet (fournies par le RPi) --------------------------- */
typedef struct
{
    uint32_t transaction;  /* 0 à 999999 (T04)           */
    uint8_t  place;        /* 1 à 14                      */
    uint8_t  annee;        /* années depuis 2000          */
    uint8_t  mois;
    uint8_t  jour;
    uint8_t  heure;
    uint8_t  minute;
    uint8_t  seconde;
} DonneesBillet;

/* --- Logique T05 (à appeler depuis la boucle principale) ----------------- */
void Impression_Init(void);
void Impression_Task(void);   /* délais d'appariement et fin d'envoi UART */
void Impression_TraiterCommandeCAN(const uint8_t *data, uint8_t dlc);   /* 0x360 */
void Impression_TraiterDateCAN(const uint8_t *data, uint8_t dlc);       /* 0x361 */
bool Impression_EstOccupee(void);

/* --- Outils (étapes 2 et 3) ---------------------------------------------- */
bool Impression_ComposerBillet(const DonneesBillet *d, EscPosTampon *t);
void Impression_DecoderCommande(const uint8_t *data, DonneesBillet *d);
void Impression_DecoderDate(const uint8_t *data, DonneesBillet *d);

#endif /* IMPRESSION_H */
