/*
 * t07_del.h
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald (T07)
 *
 * T07 — DEL de places et éclairage (Protocole CAN v1.6, section 8).
 *
 * Ce module est le même sur les trois STM32 ; la configuration du nœud
 * (places, niveau d'éclairage, identifiants de réponse) vient de
 * T07_ConfigDuNoeud(), choisie par ESA_NOEUD (esa_noeud.h).
 *
 * Commandes reçues :
 *   0x340 DEL_PLACE_CMD  [seq, place 1-14, R, G, B, mode 0 fixe / 1 clignotement 1 Hz]
 *   0x130 ECLAIRAGE_CMD  [seq, niveau 0-2, R, G, B]
 * Réponses (DLC 3) : [seq, place ou niveau, 0 refusé / 1 appliqué]
 *   0x341 / 0x342 (DEL BAS / HAUT), 0x350 / 0x351 / 0x352 (éclairage BAS / HAUT / BORNE)
 *
 * Règles :
 *   - une place ou un niveau valide qui appartient à un autre nœud est ignoré, sans réponse ;
 *   - une valeur hors plage (place 0 ou > 14, niveau > 2, mode > 1) ou un DLC
 *     incorrect est refusé (réponse « 0 ») et ne change rien ;
 *   - le module n'interprète pas les états logiques : il applique les couleurs
 *     transmises par le RPi.
 *
 * Comportement sûr :
 *   - au démarrage : témoins éteints, éclairage blanc modéré ;
 *   - perte du RPi (signalée par T07_SignalerRpi(false)) : témoins en jaune
 *     clignotant, éclairage conservé ; chaque place revient à la normale
 *     quand le RPi lui renvoie une consigne.
 */

#ifndef INC_T07_DEL_H_
#define INC_T07_DEL_H_

#include <stdbool.h>
#include <stdint.h>
#include "rgb_led_chain.h"

/* ---- Paramètres ---- */
#define T07_LUMINOSITE_GLOBALE        31u    /* 0 à 31 (5 bits) ; baisser pour limiter le courant */
#define T07_ECLAIRAGE_DEMARRAGE_R     64u    /* blanc modéré au démarrage */
#define T07_ECLAIRAGE_DEMARRAGE_V     64u
#define T07_ECLAIRAGE_DEMARRAGE_B     64u
#define T07_DEMI_PERIODE_CLIGNOTEMENT_MS 500u /* 1 Hz : 500 ms allumé, 500 ms éteint */
#define T07_INCONNU_R                 255u   /* jaune clignotant après une perte du RPi */
#define T07_INCONNU_V                 255u
#define T07_INCONNU_B                 0u
#define T07_MAX_PLACES_NOEUD          7u

/* Fonction d'envoi d'une trame CAN (ex. CanEsa_Envoyer). */
typedef bool (*T07_EnvoyerTrame)(uint16_t id, const uint8_t *data, uint8_t dlc);

typedef struct
{
    uint16_t       id_reponse_del;        /* 0x341 / 0x342 ; 0 si le nœud n'a pas de témoins */
    uint16_t       id_reponse_eclairage;  /* 0x350 / 0x351 / 0x352 */
    uint8_t        premiere_place;        /* numéro CAN de la 1re place du nœud (1 ou 8) */
    uint8_t        nb_places;             /* 7, ou 0 pour la borne */
    const uint8_t *indice_place;          /* indice dans la chaîne de la DEL de chaque place */
    uint8_t        niveau_eclairage;      /* 0, 1 ou 2 */
    const uint8_t *indices_eclairage;     /* DEL d'éclairage dans la chaîne */
    uint8_t        nb_eclairage;
    uint8_t        nb_del;                /* longueur de la chaîne */
} T07_Config;

typedef enum
{
    T07_PLACE_INITIALE = 0,   /* aucune consigne depuis le démarrage : éteinte */
    T07_PLACE_VALIDE,         /* consigne du RPi appliquée */
    T07_PLACE_INCONNUE        /* consigne perdue avec le RPi : jaune clignotant */
} T07_EtatPlace;

typedef struct
{
    T07_EtatPlace etat;
    uint8_t rouge, vert, bleu;
    uint8_t mode;             /* 0 fixe, 1 clignotement 1 Hz */
} T07_Place;

typedef struct
{
    uint32_t appliquees;
    uint32_t refusees;
    uint32_t ignorees;        /* pour un autre nœud */
    uint32_t reponses_non_envoyees;
} T07_Stats;

/* Configurations des trois nœuds (tables provisoires : à valider sur la maquette). */
extern const T07_Config T07_CONFIG_BAS;
extern const T07_Config T07_CONFIG_HAUT;
extern const T07_Config T07_CONFIG_BORNE;

/* Configuration du nœud compilé (ESA_NOEUD). */
const T07_Config *T07_ConfigDuNoeud(void);

/* Prépare la chaîne de DEL et l'état de démarrage. Rien n'est envoyé avant T07_Tache(). */
bool T07_Init(const T07_Config *config, SPI_HandleTypeDef *hspi, T07_EnvoyerTrame envoyer);

/* Traite une trame reçue (les identifiants autres que 0x340 et 0x130 sont ignorés). */
void T07_TraiterTrame(uint16_t id, uint8_t dlc, const uint8_t *data);

/* Présence du RPi, d'après la surveillance de son heartbeat. */
void T07_SignalerRpi(bool en_ligne);

/* À appeler dans la boucle principale : clignotement et mise à jour des DEL (non bloquant). */
void T07_Tache(uint32_t maintenant_ms);

/* ---- Lecture de l'état (essais, diagnostic) ---- */
bool T07_LirePlace(uint8_t place, T07_Place *resultat);       /* place CAN 1-14 de ce nœud */
void T07_LireEclairage(uint8_t *rouge, uint8_t *vert, uint8_t *bleu);
bool T07_RpiEnLigne(void);
T07_Stats T07_LireStats(void);
const RgbLedChain_HandleTypeDef *T07_Chaine(void);

#endif /* INC_T07_DEL_H_ */
