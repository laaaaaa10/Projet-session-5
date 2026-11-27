/*
 * disco.c
 *
 *  Created on: 26 nov. 2026
 *      Author: William MacDonald (T07, animation d'essai)
 *
 * Voir disco.h. La position d'une DEL autour de la carte est son rang dans la
 * zone, dans l'ordre de la chaîne (D9 à D23 font le tour de la PCB-03).
 */

#include "disco.h"
#include "t07_del.h"
#include <stddef.h>

#define ARC_PERIODE_MS            3000u   /* un tour de l'arc-en-ciel */
#define STROBE_TEMPS_MS           500u    /* 120 BPM */
#define STROBE_FLASH_MS           90u     /* durée allumée d'un flash */
#define POURSUITE_PAS_MS          60u     /* la comète avance d'une DEL (zone de 15 DEL) */
#define POURSUITE_QUEUE           5u      /* longueur de la queue (zone de 15 DEL) */

static uint8_t     s_mode = DISCO_ARRET;
static uint8_t     s_zone = DISCO_ZONE_TOUT;
static uint8_t     s_intensite = DISCO_INTENSITE_DEFAUT;
static uint32_t    s_t_debut;
static uint32_t    s_hasard = 0x2545F491u;
static T07_Couleur s_flash = { 255u, 255u, 255u };
static uint32_t    s_dernier_temps = 0xFFFFFFFFu;

static uint32_t hasard(void)                              /* xorshift32 */
{
    s_hasard ^= s_hasard << 13;
    s_hasard ^= s_hasard >> 17;
    s_hasard ^= s_hasard << 5;
    return s_hasard;
}

/* Teinte 0-255 → couleur saturée */
static T07_Couleur roue(uint8_t teinte)
{
    T07_Couleur c;
    uint8_t zone = teinte / 43u;
    uint8_t pos  = (uint8_t)((teinte - zone * 43u) * 6u);
    switch (zone)
    {
        case 0:  c.r = 255u;                  c.v = pos;                   c.b = 0u;   break;
        case 1:  c.r = (uint8_t)(255u - pos); c.v = 255u;                  c.b = 0u;   break;
        case 2:  c.r = 0u;                    c.v = 255u;                  c.b = pos;  break;
        case 3:  c.r = 0u;                    c.v = (uint8_t)(255u - pos); c.b = 255u; break;
        case 4:  c.r = pos;                   c.v = 0u;                    c.b = 255u; break;
        default: c.r = 255u;                  c.v = 0u;                    c.b = (uint8_t)(255u - pos); break;
    }
    return c;
}

static T07_Couleur attenuer(T07_Couleur c, uint32_t pour_cent)
{
    T07_Couleur s = { (uint8_t)((c.r * pour_cent) / 100u), (uint8_t)((c.v * pour_cent) / 100u),
                      (uint8_t)((c.b * pour_cent) / 100u) };
    return s;
}

static T07_Couleur couleur_arc(uint8_t k, uint8_t m, uint32_t t)
{
    uint8_t decalage = (uint8_t)(((t % ARC_PERIODE_MS) * 256u) / ARC_PERIODE_MS);
    return roue((uint8_t)(decalage + (k * 256u) / m));
}

static T07_Couleur couleur_strobe(uint32_t t)
{
    uint32_t temps = t / STROBE_TEMPS_MS;
    if (temps != s_dernier_temps)
    {
        s_dernier_temps = temps;
        if ((temps % 4u) == 3u) { T07_Couleur blanc = { 255u, 255u, 255u }; s_flash = blanc; }
        else                    { s_flash = roue((uint8_t)hasard()); }
    }
    T07_Couleur noir = { 0u, 0u, 0u };
    return ((t % STROBE_TEMPS_MS) < STROBE_FLASH_MS) ? s_flash : noir;
}

static T07_Couleur couleur_poursuite(uint8_t k, uint8_t m, uint32_t t)
{
    /* Un tour de carte dure toujours ≈ 0,9 s, quelle que soit la taille de la zone */
    uint32_t pas_ms = (POURSUITE_PAS_MS * 15u) / m;
    uint8_t  queue  = (uint8_t)((POURSUITE_QUEUE * m + 14u) / 15u);
    uint32_t pas  = t / pas_ms;
    uint8_t  tete = (uint8_t)(pas % m);
    uint8_t  tour = (uint8_t)(pas / m);
    T07_Couleur c = roue((uint8_t)(tour * 67u));            /* nouvelle couleur à chaque tour */
    uint8_t distance = (uint8_t)((tete + m - k) % m);       /* 0 = tête, puis la queue derrière */
    if (distance < queue)
    {
        return attenuer(c, 100u - (distance * 100u) / queue);
    }
    return attenuer(roue((uint8_t)(tour * 67u + 128u)), 6u); /* fond faible, couleur opposée */
}

/* Indices (dans la chaîne) des DEL de la zone ; retourne leur nombre. */
static uint8_t indices_zone(uint8_t *liste, uint8_t nb_del)
{
    const T07_Config *cfg = T07_ConfigActive();
    const uint8_t *source = NULL;
    uint8_t m = 0u;

    if (cfg == NULL)
    {
        return 0u;
    }
    switch (s_zone)
    {
        case DISCO_ZONE_PARKINGS:
            if (cfg->nb_places > 0u)        { source = cfg->indice_place;     m = cfg->nb_places; }
            else if (cfg->nb_ambiance > 0u) { source = cfg->indices_ambiance; m = cfg->nb_ambiance; }
            break;
        case DISCO_ZONE_DESSOUS:
            source = cfg->indices_eclairage; m = cfg->nb_eclairage;
            break;
        default:
            for (uint8_t i = 0u; i < nb_del; i++) { liste[i] = i; }
            return nb_del;
    }
    for (uint8_t k = 0u; k < m; k++) { liste[k] = source[k]; }
    return m;
}

/* Surcouche appelée par T07_Tache juste avant l'envoi de l'image */
static void surcouche(T07_Couleur *image, uint8_t nb_del, uint32_t maintenant_ms)
{
    uint8_t liste[RGB_LED_CHAIN_MAX_LEDS];
    uint8_t m = indices_zone(liste, nb_del);
    /* Temps arrondi à la période d'image : l'image ne change que 40 fois par seconde */
    uint32_t t = (((maintenant_ms - s_t_debut) / DISCO_PERIODE_IMAGE_MS) * DISCO_PERIODE_IMAGE_MS);

    for (uint8_t k = 0u; k < m; k++)
    {
        T07_Couleur c;
        switch (s_mode)
        {
            case DISCO_ARC_EN_CIEL: c = couleur_arc(k, m, t);       break;
            case DISCO_STROBOSCOPE: c = couleur_strobe(t);          break;
            default:                c = couleur_poursuite(k, m, t); break;
        }
        image[liste[k]] = attenuer(c, s_intensite);
    }
}

bool Disco_Choisir(uint8_t mode, uint8_t zone, uint8_t intensite, uint32_t maintenant_ms)
{
    if ((mode > DISCO_NB_MODES) || (zone > DISCO_ZONE_DESSOUS))
    {
        return false;
    }
    s_mode = mode;
    s_zone = zone;
    s_intensite = (intensite > 100u) ? 100u : intensite;
    s_t_debut = maintenant_ms;
    s_dernier_temps = 0xFFFFFFFFu;
    s_hasard ^= maintenant_ms | 1u;
    T07_DefinirSurcouche((mode == DISCO_ARRET) ? NULL : surcouche);   /* arrêt : image normale */
    return true;
}

uint8_t Disco_Mode(void)
{
    return s_mode;
}

uint8_t Disco_Zone(void)
{
    return s_zone;
}
