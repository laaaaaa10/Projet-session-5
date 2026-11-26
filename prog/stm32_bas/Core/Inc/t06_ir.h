/*
 * t06_ir.h
 *
 *  Created on: 25 nov. 2026
 *      Author: William MacDonald (T06)
 *
 * T06 — Détection de présence par infrarouge, STM32 BAS (Protocole CAN v1.6, section 6).
 *
 * Matériel (fiche C1) : une ClickBoard PCB-04 par PCB-03, sur MikroBus 1 et 2.
 *   - Le PWM 38 kHz du MikroBus passe par le TMUX1308 vers UN émetteur à la fois.
 *   - Les 8 récepteurs TSSP4038 sont lus sur le port 0 du TCA6416A (I2C) :
 *     sortie basse = porteuse reçue, haute = rien reçu.
 * Ce module ne touche pas au matériel : il passe par l'interface T06_Carte
 * (un pilote PCB-04 la fournit ; les tests sur PC la simulent).
 *
 * Balayage (non bloquant, appelé par T06_Tache) : pour chaque carte, une lecture
 * « ambiante » sans émetteur (un récepteur actif à ce moment = parasite), puis
 * chaque circuit : choix de l'émetteur, attente, lecture du récepteur associé.
 * Un changement est confirmé après T06_LECTURES_CONFIRMATION lectures identiques.
 *
 * Trames CAN :
 *   0x300 IR_BAS_CHANGEMENT [indice 0-13, état 0/1, compteur d'événements] à chaque changement confirmé
 *   0x301 IR_BAS_COMPLET   [masque 0-7, masque 8-13, compteur, validité] au démarrage après
 *                           validation, toutes les 60 s, sur demande et quand la validité change
 *   0x302 IR_LECTURE_CMD   [cible] reçue : 1 (BAS) ou 0xFF (tous) → envoi de 0x301
 *   0x080 SYNCHRO_CMD      [action] reçue : 0x01 (capteurs) ou 0x03 (tous) → envoi de 0x301
 * États CAN : 0 = absence, 1 = présence physique (et non le niveau électrique).
 * La première confirmation d'un circuit (au démarrage) n'envoie pas de 0x300.
 */

#ifndef INC_T06_IR_H_
#define INC_T06_IR_H_

#include <stdbool.h>
#include <stdint.h>

/* ---- Paramètres ---- */
#define T06_NB_CARTES_MAX            2u      /* une PCB-04 par PCB-03 */
#define T06_CIRCUITS_PAR_CARTE       8u
#define T06_NB_DETECTEURS            14u     /* indices CAN 0 à 13 */
#define T06_LECTURES_CONFIRMATION    3u      /* lectures identiques pour confirmer un état */
#define T06_DELAI_STABILISATION_MS   2u      /* choix de l'émetteur → lecture (1 à 2 ms réels) */
#define T06_PERIODE_COMPLET_MS       60000u  /* 0x301 périodique */
#define T06_DELAI_MAX_VALIDATION_MS  1000u   /* 1er 0x301 au plus tard après ce délai (validité 0 si incomplet) */

/* Sens de la détection : 1 = véhicule présent quand la porteuse est reçue (réflexion sur le
 * véhicule) ; 0 = véhicule présent quand la porteuse n'est plus reçue (faisceau coupé).
 * Relevé sur le banc le 2026-11-25 (PCB-03 du bas) : place vide → le récepteur k voit
 * l'émetteur k ; c'est donc une barrière : faisceau coupé = présence. */
#ifndef T06_PRESENCE_SI_PORTEUSE
#define T06_PRESENCE_SI_PORTEUSE     0
#endif

/* Valeurs spéciales de la table circuit → indice CAN */
#define T06_CIRCUIT_BRAS        0xFEu   /* passage du bras : lu et filtré, mais pas publié */
#define T06_CIRCUIT_INUTILISE   0xFFu   /* ni lu ni publié */

/* Interface matérielle d'une carte PCB-04 */
typedef struct
{
    /* Envoie le PWM 38 kHz vers l'émetteur « circuit » (0 à 7), ou vers aucun (-1). */
    bool (*choisir_emetteur)(void *ctx, int8_t circuit);
    /* Lit les 8 récepteurs : bit k = 1 si la sortie k est HAUTE (aucune porteuse reçue). */
    bool (*lire_recepteurs)(void *ctx, uint8_t *niveaux);
    void *ctx;
} T06_Carte;

/* Fonction d'envoi d'une trame CAN (ex. CanEsa_Envoyer). */
typedef bool (*T06_EnvoyerTrame)(uint16_t id, const uint8_t *data, uint8_t dlc);

typedef enum
{
    T06_INCONNU = 0,    /* pas encore confirmé */
    T06_ABSENCE,
    T06_PRESENCE
} T06_Etat;

typedef struct
{
    uint32_t balayages;            /* tours complets de toutes les cartes */
    uint32_t erreurs_carte;        /* échecs de choisir_emetteur ou lire_recepteurs */
    uint32_t parasites;            /* récepteur actif sans émetteur (lecture ambiante) */
    uint32_t changements;          /* 0x300 envoyés */
    uint32_t complets;             /* 0x301 envoyés */
    uint32_t trames_non_envoyees;
} T06_Stats;

/* Tables de câblage (t06_ir.c), relevées sur le banc pour les deux cartes.
 * T06_INDICE[carte][circuit]    : indice CAN 0-13, T06_CIRCUIT_BRAS ou T06_CIRCUIT_INUTILISE.
 * T06_RECEPTEUR[carte][circuit] : bit du port 0 qui lit le récepteur de cet émetteur. */
extern const uint8_t T06_INDICE[T06_NB_CARTES_MAX][T06_CIRCUITS_PAR_CARTE];
extern const uint8_t T06_RECEPTEUR[T06_NB_CARTES_MAX][T06_CIRCUITS_PAR_CARTE];

/* nb_cartes : 1 ou 2 (une seule carte sur le banc : les indices de l'autre restent inconnus). */
bool T06_Init(const T06_Carte *cartes, uint8_t nb_cartes, T06_EnvoyerTrame envoyer, uint32_t maintenant_ms);

/* À appeler dans la boucle principale (non bloquant, hormis les courts accès I2C du pilote). */
void T06_Tache(uint32_t maintenant_ms);

/* Trame CAN reçue (seules 0x302 et 0x080 sont traitées). */
void T06_TraiterTrame(uint16_t id, uint8_t dlc, const uint8_t *data);

/* ---- Lecture de l'état (console, diagnostic, démo) ---- */
T06_Etat  T06_LireDetecteur(uint8_t indice);                 /* indice CAN 0-13 */
T06_Etat  T06_LireCircuit(uint8_t carte, uint8_t circuit);   /* y compris le passage du bras */
uint8_t   T06_LireNiveauxBruts(uint8_t carte, int8_t circuit); /* port 0 lu pendant ce circuit (-1 : ambiant) */
bool      T06_CircuitParasite(uint8_t carte, uint8_t circuit); /* récepteur actif sans émetteur */
uint8_t   T06_NbCartes(void);
bool      T06_EstValide(void);
T06_Stats T06_LireStats(void);

#endif /* INC_T06_IR_H_ */
