/*
 * essai_t07.c
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald (T07)
 *
 * Voir essai_t07.h.
 */

#include "essai_t07.h"
#include "console.h"
#include "esa_can.h"
#include "esa_can_ids.h"
#include "noeud.h"
#include "t07_del.h"
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ESSAI_PERIODE_HB_RPI_MS  500u
#define ESSAI_MAX_JETONS         10u

static uint8_t  s_sequence = 0u;
static bool     s_hb_rpi_simule = false;
static uint8_t  s_compteur_hb_rpi = 0u;
static uint32_t s_t_hb_rpi = 0u;
static bool     s_trace_tout = false;

/* ---- Affichage des trames ---- */

static const char *nom_trame(uint16_t id)
{
    switch (id)
    {
        case CAN_ID_HEARTBEAT_RPI:        return "HEARTBEAT_RPI";
        case CAN_ID_HEARTBEAT_BAS:        return "HEARTBEAT_BAS";
        case CAN_ID_ECLAIRAGE_CMD:        return "ECLAIRAGE_CMD";
        case CAN_ID_DEL_PLACE_CMD:        return "DEL_PLACE_CMD";
        case CAN_ID_DEL_BAS_ETAT:         return "DEL_BAS_ETAT";
        case CAN_ID_DEL_HAUT_ETAT:        return "DEL_HAUT_ETAT";
        case CAN_ID_ECLAIRAGE_BAS_ETAT:   return "ECLAIRAGE_BAS_ETAT";
        case CAN_ID_ECLAIRAGE_HAUT_ETAT:  return "ECLAIRAGE_HAUT_ETAT";
        case CAN_ID_ECLAIRAGE_BORNE_ETAT: return "ECLAIRAGE_BORNE_ETAT";
        default:                          return "";
    }
}

static void afficher_brut(const char *sens, uint16_t id, uint8_t dlc, const uint8_t *data)
{
    char texte[64];
    int n = 0;
    for (uint8_t i = 0u; (i < dlc) && (i < 8u); i++)
    {
        n += snprintf(&texte[n], sizeof texte - (size_t)n, " %02X", data[i]);
    }
    texte[n] = '\0';
    Console_Printf("%s 0x%03X %-20s DLC %u :%s\r\n", sens, id, nom_trame(id), dlc, texte);
}

/* Appelée par Noeud_Tache() pour chaque trame reçue */
static void observer_trame(const TrameCan *t)
{
    bool reponse_t07 = (t->id == CAN_ID_DEL_BAS_ETAT) || (t->id == CAN_ID_DEL_HAUT_ETAT) ||
                       (t->id == CAN_ID_ECLAIRAGE_BAS_ETAT) || (t->id == CAN_ID_ECLAIRAGE_HAUT_ETAT) ||
                       (t->id == CAN_ID_ECLAIRAGE_BORNE_ETAT);

    if (reponse_t07 && (t->dlc == 3u))
    {
        bool del = (t->id == CAN_ID_DEL_BAS_ETAT) || (t->id == CAN_ID_DEL_HAUT_ETAT);
        Console_Printf("<- 0x%03X %s : seq=%u %s=%u -> %s\r\n", t->id, nom_trame(t->id),
                       t->data[0], del ? "place" : "niveau", t->data[1],
                       (t->data[2] == 1u) ? "APPLIQUE" : "REFUSE");
    }
    else if (s_trace_tout)
    {
        afficher_brut("<-", t->id, t->dlc, t->data);
    }
}

/* ---- Commandes ---- */

static void envoyer(uint16_t id, const uint8_t *data, uint8_t dlc)
{
    afficher_brut("->", id, dlc, data);
    if (!CanEsa_Envoyer(id, data, dlc))
    {
        Console_Ecrire("   ERREUR : aucune boite d'emission CAN libre\r\n");
    }
}

static void cmd_aide(void)
{
    Console_Ecrire("Commandes :\r\n"
                   "  del <place> <R> <V> <B> [mode]   0x340 (mode 0 fixe, 1 clignote)\r\n"
                   "  ecl <niveau> <R> <V> <B>         0x130\r\n"
                   "  brut <id hex> [octets hex...]    trame quelconque\r\n"
                   "  hb on | hb off                   heartbeat RPi simule (0x040)\r\n"
                   "  etat                             places, eclairage, compteurs\r\n"
                   "  image                            couleurs envoyees aux 15 DEL\r\n"
                   "  trace on | trace off             toutes les trames recues\r\n");
}

static void cmd_del(char **j, uint8_t n)
{
    if ((n < 5u) || (n > 6u))
    {
        Console_Ecrire("Usage : del <place> <R> <V> <B> [mode]\r\n");
        return;
    }
    uint8_t d[6] = { s_sequence++, (uint8_t)strtoul(j[1], NULL, 0), (uint8_t)strtoul(j[2], NULL, 0),
                     (uint8_t)strtoul(j[3], NULL, 0), (uint8_t)strtoul(j[4], NULL, 0),
                     (n == 6u) ? (uint8_t)strtoul(j[5], NULL, 0) : 0u };
    envoyer(CAN_ID_DEL_PLACE_CMD, d, 6u);
}

static void cmd_ecl(char **j, uint8_t n)
{
    if (n != 5u)
    {
        Console_Ecrire("Usage : ecl <niveau> <R> <V> <B>\r\n");
        return;
    }
    uint8_t d[5] = { s_sequence++, (uint8_t)strtoul(j[1], NULL, 0), (uint8_t)strtoul(j[2], NULL, 0),
                     (uint8_t)strtoul(j[3], NULL, 0), (uint8_t)strtoul(j[4], NULL, 0) };
    envoyer(CAN_ID_ECLAIRAGE_CMD, d, 5u);
}

static void cmd_brut(char **j, uint8_t n)
{
    if ((n < 2u) || (n > 10u))
    {
        Console_Ecrire("Usage : brut <id hex> [0 a 8 octets hex]\r\n");
        return;
    }
    uint8_t d[8] = { 0 };
    uint8_t dlc = (uint8_t)(n - 2u);
    for (uint8_t i = 0u; i < dlc; i++)
    {
        d[i] = (uint8_t)strtoul(j[2u + i], NULL, 16);
    }
    envoyer((uint16_t)strtoul(j[1], NULL, 16), d, dlc);
}

static const char *nom_etat_place(T07_EtatPlace e)
{
    switch (e)
    {
        case T07_PLACE_VALIDE:   return "valide  ";
        case T07_PLACE_INCONNUE: return "INCONNUE";
        default:                 return "initiale";
    }
}

static void cmd_etat(void)
{
    const T07_Config *cfg = T07_ConfigDuNoeud();
    T07_Stats s = T07_LireStats();
    CanEsa_Stats c = CanEsa_LireStats();
    uint8_t r, v, b;

    Console_Printf("RPi : %s | heartbeat simule : %s | CAN %s\r\n",
                   Noeud_RpiEnLigne() ? "EN LIGNE" : "hors ligne",
                   s_hb_rpi_simule ? "oui" : "non",
                   CanEsa_EnLoopback() ? "loopback" : "normal");
    for (uint8_t i = 0u; i < cfg->nb_places; i++)
    {
        T07_Place p;
        uint8_t place = (uint8_t)(cfg->premiere_place + i);
        if (T07_LirePlace(place, &p))
        {
            Console_Printf("  place %2u (DEL %2u) : %s  R=%3u V=%3u B=%3u  %s\r\n",
                           place, cfg->indice_place[i], nom_etat_place(p.etat),
                           p.rouge, p.vert, p.bleu, (p.mode == 1u) ? "clignote" : "fixe");
        }
    }
    T07_LireEclairage(&r, &v, &b);
    Console_Printf("  eclairage niveau %u : R=%u V=%u B=%u\r\n", cfg->niveau_eclairage, r, v, b);
    Console_Printf("T07 : %lu appliquees, %lu refusees, %lu ignorees, %lu reponses non envoyees\r\n",
                   (unsigned long)s.appliquees, (unsigned long)s.refusees,
                   (unsigned long)s.ignorees, (unsigned long)s.reponses_non_envoyees);
    Console_Printf("CAN : %lu recues, %lu envoyees, %lu perdues RX, %lu refusees TX, %lu annulees TX\r\n",
                   (unsigned long)c.recues, (unsigned long)c.envoyees, (unsigned long)c.perdues_rx,
                   (unsigned long)c.refusees_tx, (unsigned long)c.annulees_tx);
}

static void cmd_image(void)
{
    const RgbLedChain_HandleTypeDef *ch = T07_Chaine();
    for (uint8_t i = 0u; i < ch->led_count; i++)
    {
        const uint8_t *p = &ch->tx_frame[RGB_LED_CHAIN_START_BYTES + 4u * i];
        Console_Printf("  DEL %2u (D%2u) : R=%3u V=%3u B=%3u lum=%2u\r\n",
                       i, 9u + i, p[3], p[2], p[1], p[0] & 0x1Fu);
    }
}

static void executer(char *ligne)
{
    char *jetons[ESSAI_MAX_JETONS];
    uint8_t n = 0u;
    char *t = strtok(ligne, " \t");
    while ((t != NULL) && (n < ESSAI_MAX_JETONS))
    {
        jetons[n++] = t;
        t = strtok(NULL, " \t");
    }
    if (n == 0u)
    {
        return;
    }

    if      (strcmp(jetons[0], "aide") == 0)  { cmd_aide(); }
    else if (strcmp(jetons[0], "del") == 0)   { cmd_del(jetons, n); }
    else if (strcmp(jetons[0], "ecl") == 0)   { cmd_ecl(jetons, n); }
    else if (strcmp(jetons[0], "brut") == 0)  { cmd_brut(jetons, n); }
    else if (strcmp(jetons[0], "etat") == 0)  { cmd_etat(); }
    else if (strcmp(jetons[0], "image") == 0) { cmd_image(); }
    else if ((strcmp(jetons[0], "hb") == 0) && (n == 2u))
    {
        s_hb_rpi_simule = (strcmp(jetons[1], "on") == 0);
        Console_Printf("Heartbeat RPi simule : %s\r\n", s_hb_rpi_simule ? "oui" : "non");
    }
    else if ((strcmp(jetons[0], "trace") == 0) && (n == 2u))
    {
        s_trace_tout = (strcmp(jetons[1], "on") == 0);
        Console_Printf("Trace de toutes les trames : %s\r\n", s_trace_tout ? "oui" : "non");
    }
    else
    {
        Console_Ecrire("Commande inconnue (taper aide)\r\n");
    }
}

/* ---- Interface ---- */

void EssaiT07_Init(void)
{
    Noeud_DefinirObservateur(observer_trame);
    Console_Ecrire("\r\n=== Essai T07 (STM32 BAS) ===\r\n");
    Console_Printf("CAN en %s. Taper aide.\r\n", CanEsa_EnLoopback() ? "loopback" : "mode normal");
}

void EssaiT07_Tache(uint32_t maintenant_ms)
{
    char ligne[80];

    if (Console_LireLigne(ligne, sizeof ligne))
    {
        executer(ligne);
    }

    if (s_hb_rpi_simule && ((maintenant_ms - s_t_hb_rpi) >= ESSAI_PERIODE_HB_RPI_MS))
    {
        uint8_t d[2] = { s_compteur_hb_rpi++, HEARTBEAT_ETAT_PRET };
        s_t_hb_rpi = maintenant_ms;
        CanEsa_Envoyer(CAN_ID_HEARTBEAT_RPI, d, 2u);
        if (s_trace_tout)
        {
            afficher_brut("->", CAN_ID_HEARTBEAT_RPI, 2u, d);
        }
    }
}
