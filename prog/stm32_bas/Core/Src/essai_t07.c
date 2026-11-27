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
#include "esa_noeud.h"
#include "esa_can_ids.h"
#include "noeud.h"
#include "t07_del.h"
#include "disco.h"
#if (ESA_NOEUD == ESA_NOEUD_BAS)
#include "essai_t06.h"
#endif
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
/* ecl tous : trames en attente, envoyées une à la fois (3 boîtes d'émission CAN seulement)
 * bits 0-2 = 0x130 des niveaux 0 à 2 (les parkings du haut ne sont pas touchés) */
#define ECL_TOUS_ESPACEMENT_MS 2u
static uint8_t  s_ecl_tous_a_envoyer = 0u;
static uint8_t  s_ecl_tous_rvb[3];
static uint32_t s_t_ecl_tous = 0u;

/* ---- Affichage des trames ---- */

static const char *nom_trame(uint16_t id)
{
    switch (id)
    {
        case CAN_ID_HEARTBEAT_RPI:        return "HEARTBEAT_RPI";
        case CAN_ID_HEARTBEAT_HAUT:       return "HEARTBEAT_HAUT";
        case CAN_ID_HEARTBEAT_BAS:        return "HEARTBEAT_BAS";
        case CAN_ID_HEARTBEAT_BORNE:      return "HEARTBEAT_BORNE";
        case CAN_ID_ECLAIRAGE_CMD:        return "ECLAIRAGE_CMD";
        case CAN_ID_DEL_PLACE_CMD:        return "DEL_PLACE_CMD";
        case CAN_ID_DEL_PLACES_1_7_ETAT:  return "DEL_PLACES_1_7_ETAT";
        case CAN_ID_DEL_PLACES_8_14_ETAT: return "DEL_PLACES_8_14_ETAT";
        case CAN_ID_ECLAIRAGE_NIV0_ETAT:  return "ECLAIRAGE_NIV0_ETAT";
        case CAN_ID_ECLAIRAGE_NIV1_ETAT:  return "ECLAIRAGE_NIV1_ETAT";
        case CAN_ID_ECLAIRAGE_NIV2_ETAT:  return "ECLAIRAGE_NIV2_ETAT";
        case CAN_ID_ESSAI_DISCO:          return "ESSAI_DISCO";
        case CAN_ID_ESSAI_AMBIANCE:       return "ESSAI_AMBIANCE";
#if (ESA_NOEUD == ESA_NOEUD_BAS)
        default:                          return EssaiT06_NomTrame(id);
#else
        default:                          return "";
#endif
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
static const char *nom_disco(uint8_t mode)
{
    switch (mode)
    {
        case DISCO_ARC_EN_CIEL: return "arc-en-ciel";
        case DISCO_STROBOSCOPE: return "stroboscope";
        case DISCO_POURSUITE:   return "poursuite";
        default:                return "arret";
    }
}

static const char *nom_zone(uint8_t zone)
{
    switch (zone)
    {
        case DISCO_ZONE_PARKINGS: return "parkings";
        case DISCO_ZONE_DESSOUS:  return "dessous";
        default:                  return "tout";
    }
}

static void appliquer_disco(uint8_t mode, uint8_t zone, uint8_t intensite)
{
    if (Disco_Choisir(mode, zone, intensite, HAL_GetTick()))
    {
        Console_Printf("Disco sur ce noeud : %s, zone %s (%u %%)\r\n", nom_disco(mode), nom_zone(zone), intensite);
    }
}

static void appliquer_ambiance(uint8_t r, uint8_t v, uint8_t b)
{
    if (T07_ReglerAmbiance(r, v, b))
    {
        Console_Printf("Ambiance des parkings sur ce noeud : R=%u V=%u B=%u\r\n", r, v, b);
    }
}

static void observer_trame(const TrameCan *t)
{
    if (t->id == CAN_ID_ESSAI_DISCO)
    {
        if ((t->dlc >= 3u) && ((t->data[1] == ESA_NOEUD) || (t->data[1] == DISCO_CIBLE_TOUS)))
        {
            appliquer_disco(t->data[0], (t->dlc >= 4u) ? t->data[3] : DISCO_ZONE_TOUT, t->data[2]);
        }
        return;
    }
    if (t->id == CAN_ID_ESSAI_AMBIANCE)
    {
        if (t->dlc >= 3u)
        {
            appliquer_ambiance(t->data[0], t->data[1], t->data[2]);   /* seul le HAUT a une ambiance */
        }
        return;
    }
#if (ESA_NOEUD == ESA_NOEUD_BAS)
    if ((t->id == CAN_ID_IR_BAS_CHANGEMENT) || (t->id == CAN_ID_IR_BAS_COMPLET))
    {
        EssaiT06_ObserverTrame(t);
        return;
    }
#endif
    bool reponse_t07 = (t->id == CAN_ID_DEL_PLACES_1_7_ETAT) || (t->id == CAN_ID_DEL_PLACES_8_14_ETAT) ||
                       (t->id == CAN_ID_ECLAIRAGE_NIV0_ETAT) || (t->id == CAN_ID_ECLAIRAGE_NIV1_ETAT) ||
                       (t->id == CAN_ID_ECLAIRAGE_NIV2_ETAT);

    if (reponse_t07 && (t->dlc == 3u))
    {
        bool del = (t->id == CAN_ID_DEL_PLACES_1_7_ETAT) || (t->id == CAN_ID_DEL_PLACES_8_14_ETAT);
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

/* Ce nœud ne reçoit pas ses propres trames (ni écho local ni loopback) */
static bool sans_retour_local(void)
{
    return !CanEsa_EchoLocal() && !CanEsa_EnLoopback();
}

/* Envoie 0x130 ; sans retour local, la commande est aussi traitée par ce nœud */
static bool envoyer_eclairage(uint8_t niveau, uint8_t r, uint8_t v, uint8_t b)
{
    uint8_t d[5] = { s_sequence, niveau, r, v, b };
    if (!CanEsa_Envoyer(CAN_ID_ECLAIRAGE_CMD, d, 5u))
    {
        return false;
    }
    s_sequence++;
    afficher_brut("->", CAN_ID_ECLAIRAGE_CMD, 5u, d);
    if (sans_retour_local())
    {
        T07_TraiterTrame(CAN_ID_ECLAIRAGE_CMD, 5u, d);
    }
    return true;
}

static void cmd_aide(void)
{
    Console_Ecrire("Commandes :\r\n"
                   "  del <place> <R> <V> <B> [mode]   0x340 (mode 0 fixe, 1 clignote)\r\n"
                   "  ecl <niveau> <R> <V> <B>         0x130\r\n"
                   "  ecl <niveau> <couleur> [int. %]  ex. ecl 0 blanc 30, ecl 0 bleu 100\r\n"
                   "  brut <id hex> [octets hex...]    trame quelconque\r\n"
                   "  hb on | hb off                   heartbeat RPi simule (0x040)\r\n"
                   "  etat                             places, eclairage, compteurs\r\n"
                   "  image                            couleurs envoyees aux 15 DEL\r\n"
                   "  trace on | trace off             toutes les trames recues\r\n"
                   "  ecl parkings <couleur> [int. %]  ambiance des parkings du haut (rouge au depart)\r\n"
                   "  ecl tous <couleur> [int. %]      niveaux 0, 1 et 2 (pas les parkings), ex. ecl tous blanc 10\r\n"
                   "  disco <off|1|2|3> [cible] [zone] [int. %]\r\n"
                   "                                   1 arc-en-ciel, 2 stroboscope, 3 poursuite\r\n"
                   "                                   cible : haut (defaut), bas, milieu, tous\r\n"
                   "                                   zone : tout (defaut), parkings, dessous\r\n");
#if (ESA_NOEUD == ESA_NOEUD_BAS)
    EssaiT06_Aide();
    Console_Ecrire("  banc bas | banc milieu            banc : les DEL montrent les places 1-7 (niv. 0)\r\n"
                   "                                   ou 8-14 (niv. 1)\r\n");
#endif
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

/* Couleurs nommées pour la commande ecl */
typedef struct { const char *nom; uint8_t r, v, b; } CouleurNommee;
static const CouleurNommee COULEURS[] =
{
    { "blanc", 255u, 255u, 255u }, { "chaud", 255u, 160u, 60u }, { "rouge", 255u, 0u, 0u },
    { "vert", 0u, 255u, 0u },      { "bleu", 0u, 0u, 255u },     { "jaune", 255u, 255u, 0u },
    { "orange", 255u, 165u, 0u },  { "violet", 160u, 0u, 255u }, { "cyan", 0u, 255u, 255u },
    { "eteint", 0u, 0u, 0u },
};

static bool chercher_couleur(const char *nom, uint8_t *r, uint8_t *v, uint8_t *b)
{
    for (uint8_t i = 0u; i < (uint8_t)(sizeof COULEURS / sizeof COULEURS[0]); i++)
    {
        if (strcmp(nom, COULEURS[i].nom) == 0)
        {
            *r = COULEURS[i].r; *v = COULEURS[i].v; *b = COULEURS[i].b;
            return true;
        }
    }
    return false;
}

/* ecl <niveau> <R> <V> <B>   ou   ecl <niveau> <couleur> [intensite 0-100 %] */
#if (ESA_NOEUD == ESA_NOEUD_BAS)
/* Banc avec une seule Discovery et une seule chaîne de DEL : les PCB-03 branchées en
 * parallèle sur le même PCB-11 affichent la même image. On choisit donc ce que l'image
 * représente : le BAS (places 1-7 + éclairage niveau 0) ou le milieu (places 8-14 +
 * éclairage niveau 1, configuration de la BORNE). La détection IR des 14 places, elle,
 * reste complète. */
static void cmd_banc(char **j, uint8_t n)
{
    const T07_Config *cfg = NULL;
    const char *texte = "";

    if ((n == 2u) && (strcmp(j[1], "bas") == 0))
    {
        cfg = &T07_CONFIG_BAS_BANC;
        texte = "places 1 a 7 et eclairage du niveau 0 (ecl 0 ...)";
    }
    else if ((n == 2u) && (strcmp(j[1], "milieu") == 0))
    {
        cfg = &T07_CONFIG_BORNE;
        texte = "places 8 a 14 et eclairage du niveau 1 (ecl 1 ...)";
    }
    else
    {
        Console_Ecrire("Usage : banc bas | banc milieu\r\n");
        return;
    }

    SPI_HandleTypeDef *hspi = T07_Chaine()->hspi;
    uint32_t t0 = HAL_GetTick();
    while ((hspi->State != HAL_SPI_STATE_READY) && ((HAL_GetTick() - t0) < 10u)) { }  /* fin du DMA en cours */
    if (!T07_Init(cfg, hspi, CanEsa_Envoyer))
    {
        Console_Ecrire("ERREUR : T07_Init\r\n");
        return;
    }
    Console_Printf("Les DEL affichent maintenant : %s\r\n", texte);
    EssaiT06_RafraichirDemo();
}
#endif

/* disco <off|1|2|3> [haut|bas|milieu|tous] [tout|parkings|dessous] [intensite %]
 * (les options dans n'importe quel ordre) : trame d'essai 0x7F0 */
static void cmd_disco(char **j, uint8_t n)
{
    uint8_t mode, cible = 2u, zone = DISCO_ZONE_TOUT, intensite = DISCO_INTENSITE_DEFAUT;

    if ((n >= 2u) && (strcmp(j[1], "off") == 0))                         { mode = DISCO_ARRET; }
    else if ((n >= 2u) && (j[1][0] >= '1') && (j[1][0] <= '3') && (j[1][1] == '\0'))
    {
        mode = (uint8_t)(j[1][0] - '0');
    }
    else
    {
        Console_Ecrire("Usage : disco <off|1|2|3> [haut|bas|milieu|tous] [tout|parkings|dessous] [intensite %]\r\n"
                       "        1 arc-en-ciel, 2 stroboscope, 3 poursuite\r\n");
        return;
    }
    for (uint8_t k = 2u; k < n; k++)
    {
        if ((j[k][0] >= '0') && (j[k][0] <= '9'))
        {
            unsigned long v = strtoul(j[k], NULL, 0);
            intensite = (uint8_t)((v > 100u) ? 100u : v);
        }
        else if (strcmp(j[k], "bas") == 0)      { cible = 1u; }
        else if (strcmp(j[k], "haut") == 0)     { cible = 2u; }
        else if (strcmp(j[k], "milieu") == 0)   { cible = 3u; }
        else if (strcmp(j[k], "tous") == 0)     { cible = DISCO_CIBLE_TOUS; }
        else if (strcmp(j[k], "tout") == 0)     { zone = DISCO_ZONE_TOUT; }
        else if (strcmp(j[k], "parkings") == 0) { zone = DISCO_ZONE_PARKINGS; }
        else if (strcmp(j[k], "dessous") == 0)  { zone = DISCO_ZONE_DESSOUS; }
        else
        {
            Console_Printf("Option inconnue : %s (cibles : haut bas milieu tous ; zones : tout parkings dessous)\r\n", j[k]);
            return;
        }
    }

    uint8_t d[4] = { mode, cible, intensite, zone };
    Console_Printf("-> 0x7F0 ESSAI_DISCO : %s, cible %s, zone %s, %u %%\r\n", nom_disco(mode),
                   (cible == 1u) ? "bas" : (cible == 2u) ? "haut" : (cible == 3u) ? "milieu" : "tous",
                   nom_zone(zone), intensite);
    envoyer(CAN_ID_ESSAI_DISCO, d, 4u);
    /* Sans écho local ni loopback, ce nœud ne reçoit pas sa propre trame : on l'applique ici */
    if (!CanEsa_EchoLocal() && !CanEsa_EnLoopback() &&
        ((cible == ESA_NOEUD) || (cible == DISCO_CIBLE_TOUS)))
    {
        appliquer_disco(mode, zone, intensite);
    }
}

static void cmd_ecl(char **j, uint8_t n)
{
    uint8_t r, v, b;
    bool ambiance = (n >= 2u) && (strcmp(j[1], "parkings") == 0);   /* ecl parkings ... : trame d'essai 0x7F1 */
    bool tous     = (n >= 2u) && (strcmp(j[1], "tous") == 0);       /* niveaux 0, 1 et 2 */

    if ((n == 5u) && (j[2][0] >= '0') && (j[2][0] <= '9'))
    {
        r = (uint8_t)strtoul(j[2], NULL, 0);
        v = (uint8_t)strtoul(j[3], NULL, 0);
        b = (uint8_t)strtoul(j[4], NULL, 0);
    }
    else if (((n == 3u) || (n == 4u)) && chercher_couleur(j[2], &r, &v, &b))
    {
        uint32_t intensite = (n == 4u) ? strtoul(j[3], NULL, 0) : 100u;
        if (intensite > 100u) { intensite = 100u; }
        r = (uint8_t)(((uint32_t)r * intensite + 50u) / 100u);
        v = (uint8_t)(((uint32_t)v * intensite + 50u) / 100u);
        b = (uint8_t)(((uint32_t)b * intensite + 50u) / 100u);
    }
    else
    {
        Console_Ecrire("Usage : ecl <niveau|parkings|tous> <R> <V> <B>  ou  ecl <niveau|parkings|tous> <couleur> [intensite %]\r\n"
                       "Couleurs : blanc chaud rouge vert bleu jaune orange violet cyan eteint\r\n");
        return;
    }
    if (tous)
    {
        s_ecl_tous_rvb[0] = r; s_ecl_tous_rvb[1] = v; s_ecl_tous_rvb[2] = b;
        s_ecl_tous_a_envoyer = 0x07u;                    /* envoyé par EssaiT07_Tache */
        Console_Printf("-> ecl tous : niveaux 0, 1 et 2, R=%u V=%u B=%u\r\n", r, v, b);
        return;
    }
    if (ambiance)
    {
        uint8_t d[3] = { r, v, b };
        Console_Printf("-> 0x7F1 ESSAI_AMBIANCE : parkings du haut, R=%u V=%u B=%u\r\n", r, v, b);
        envoyer(CAN_ID_ESSAI_AMBIANCE, d, 3u);
        if (sans_retour_local())
        {
            appliquer_ambiance(r, v, b);                  /* sur le HAUT lui-même */
        }
        return;
    }
    uint8_t niveau = (uint8_t)strtoul(j[1], NULL, 0);
    Console_Printf("-> 0x130 ECLAIRAGE_CMD : niveau %u, R=%u V=%u B=%u\r\n", niveau, r, v, b);
    if (!envoyer_eclairage(niveau, r, v, b))
    {
        Console_Ecrire("   ERREUR : aucune boite d'emission CAN libre\r\n");
    }
}

/* ecl tous : une trame à la fois, espacées de 2 ms (laisse de la place aux réponses) */
static void envoyer_ecl_tous(uint32_t maintenant_ms)
{
    if ((s_ecl_tous_a_envoyer == 0u) || ((maintenant_ms - s_t_ecl_tous) < ECL_TOUS_ESPACEMENT_MS))
    {
        return;
    }
    for (uint8_t niveau = 0u; niveau < 3u; niveau++)
    {
        if ((s_ecl_tous_a_envoyer & (1u << niveau)) != 0u)
        {
            if (envoyer_eclairage(niveau, s_ecl_tous_rvb[0], s_ecl_tous_rvb[1], s_ecl_tous_rvb[2]))
            {
                s_ecl_tous_a_envoyer &= (uint8_t)~(1u << niveau);
                s_t_ecl_tous = maintenant_ms;
            }
            return;                                       /* boîtes pleines : on réessaie au prochain appel */
        }
    }
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
    const T07_Config *cfg = (T07_ConfigActive() != NULL) ? T07_ConfigActive() : T07_ConfigDuNoeud();
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
    if (cfg->nb_eclairage > 0u)
    {
        T07_LireEclairage(&r, &v, &b);
        Console_Printf("  eclairage niveau %u : R=%u V=%u B=%u\r\n", cfg->niveau_eclairage, r, v, b);
    }
    else
    {
        Console_Printf("  eclairage niveau %u : aucune DEL (commandes refusees)\r\n", cfg->niveau_eclairage);
    }
    if (T07_LireAmbiance(&r, &v, &b))
    {
        Console_Printf("  ambiance parkings : R=%u V=%u B=%u (ecl parkings ...)\r\n", r, v, b);
    }
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
    else if (strcmp(jetons[0], "disco") == 0) { cmd_disco(jetons, n); }
#if (ESA_NOEUD == ESA_NOEUD_BAS)
    else if (strcmp(jetons[0], "banc") == 0)  { cmd_banc(jetons, n); }
#endif
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
#if (ESA_NOEUD == ESA_NOEUD_BAS)
    else if (EssaiT06_Executer(jetons, n)) { /* commande T06 */ }
#endif
    else
    {
        Console_Ecrire("Commande inconnue (taper aide)\r\n");
    }
}

/* ---- Interface ---- */

void EssaiT07_Init(void)
{
    Noeud_DefinirObservateur(observer_trame);
#if (ESA_NOEUD == ESA_NOEUD_BAS)
    Console_Ecrire("\r\n=== Essai T06 / T07 (STM32 BAS) ===\r\n");
#elif (ESA_NOEUD == ESA_NOEUD_HAUT)
    Console_Ecrire("\r\n=== Essai T07 (STM32 HAUT) ===\r\n");
#else
    Console_Ecrire("\r\n=== Essai T07 (STM32 BORNE) ===\r\n");
#endif
    Console_Printf("CAN en %s. Taper aide.\r\n", CanEsa_EnLoopback() ? "loopback" : "mode normal");
}

void EssaiT07_Tache(uint32_t maintenant_ms)
{
    char ligne[80];

    if (Console_LireLigne(ligne, sizeof ligne))
    {
        executer(ligne);
    }
    envoyer_ecl_tous(maintenant_ms);

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
