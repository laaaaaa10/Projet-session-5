/*
 * t07_del.c
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald (T07)
 *
 * Voir t07_del.h.
 */

#include "t07_del.h"
#include "esa_can_ids.h"
#include "esa_noeud.h"
#include <string.h>

#define DLC_DEL_PLACE_CMD    6u
#define DLC_ECLAIRAGE_CMD    5u
#define DLC_REPONSE          3u
#define PLACE_MIN            1u
#define PLACE_MAX            14u
#define NIVEAU_MAX           2u
#define MODE_MAX             1u
#define RESULTAT_REFUSE      0u
#define RESULTAT_APPLIQUE    1u

/* ---- Tables des nœuds ----
 * Répartition décidée par l'équipe le 2026-11-25 : trois PCB-03 empilées, chacune
 * commandée par le PCB-11 d'un STM32 :
 *   - PCB-03 du bas    → STM32 BAS   : places 1 à 7 ; DEL du dessous éteintes ;
 *   - PCB-03 du milieu → STM32 BORNE : places 8 à 14 + éclairage du niveau 1 ;
 *   - PCB-03 du haut   → STM32 HAUT  : éclairage du niveau 2 ; témoins du dessus éteints.
 * Le niveau 0 n'a pas de DEL : le BAS en refuse les commandes (réponse 0x350 « refusé »).
 * Les identifiants de réponse suivent la fonction (voir esa_can_ids.h).
 *
 * PCB-03 (15 DEL, D9 = indice 0), vérifiée sur la carte le 2026-11-25 :
 * indices impairs (D10, D12, …, D22) = 7 témoins sur le dessus, dans le sens horaire
 * vu de dessus à partir de la place au-dessus de l'entrée ; indices pairs = éclairage
 * sous la carte. Numérotation des places (place 1 = D10) : à confirmer avec l'équipe. */
static const uint8_t PCB03_INDICES_PLACES[T07_MAX_PLACES_NOEUD] = { 1u, 3u, 5u, 7u, 9u, 11u, 13u };
static const uint8_t PCB03_INDICES_ECLAIRAGE[] = { 0u, 2u, 4u, 6u, 8u, 10u, 12u, 14u };
#define PCB03_NB_DEL   15u

const T07_Config T07_CONFIG_BAS =
{
    .id_reponse_del       = CAN_ID_DEL_PLACES_1_7_ETAT,
    .id_reponse_eclairage = CAN_ID_ECLAIRAGE_NIV0_ETAT,
    .premiere_place       = 1u,
    .nb_places            = 7u,
    .indice_place         = PCB03_INDICES_PLACES,
    .niveau_eclairage     = 0u,
    .indices_eclairage    = NULL,                 /* niveau 0 non éclairé : commandes refusées */
    .nb_eclairage         = 0u,
    .nb_del               = PCB03_NB_DEL,
};

const T07_Config T07_CONFIG_BORNE =
{
    .id_reponse_del       = CAN_ID_DEL_PLACES_8_14_ETAT,
    .id_reponse_eclairage = CAN_ID_ECLAIRAGE_NIV1_ETAT,
    .premiere_place       = 8u,
    .nb_places            = 7u,
    .indice_place         = PCB03_INDICES_PLACES,
    .niveau_eclairage     = 1u,
    .indices_eclairage    = PCB03_INDICES_ECLAIRAGE,
    .nb_eclairage         = (uint8_t)sizeof(PCB03_INDICES_ECLAIRAGE),
    .nb_del               = PCB03_NB_DEL,
};

const T07_Config T07_CONFIG_HAUT =
{
    .id_reponse_del       = 0u,                   /* pas de places : les témoins servent d'ambiance */
    .id_reponse_eclairage = CAN_ID_ECLAIRAGE_NIV2_ETAT,
    .premiere_place       = 0u,
    .nb_places            = 0u,
    .indice_place         = NULL,
    .niveau_eclairage     = 2u,
    .indices_eclairage    = PCB03_INDICES_ECLAIRAGE,
    .nb_eclairage         = (uint8_t)sizeof(PCB03_INDICES_ECLAIRAGE),
    .indices_ambiance     = PCB03_INDICES_PLACES,     /* témoins du dessus (« parkings ») */
    .nb_ambiance          = T07_MAX_PLACES_NOEUD,
    .ambiance_demarrage   = { T07_AMBIANCE_DEMARRAGE_R, T07_AMBIANCE_DEMARRAGE_V, T07_AMBIANCE_DEMARRAGE_B },
    .nb_del               = PCB03_NB_DEL,
};

const T07_Config T07_CONFIG_BAS_BANC =
{
    .id_reponse_del       = CAN_ID_DEL_PLACES_1_7_ETAT,
    .id_reponse_eclairage = CAN_ID_ECLAIRAGE_NIV0_ETAT,
    .premiere_place       = 1u,
    .nb_places            = 7u,
    .indice_place         = PCB03_INDICES_PLACES,
    .niveau_eclairage     = 0u,
    .indices_eclairage    = PCB03_INDICES_ECLAIRAGE,
    .nb_eclairage         = (uint8_t)sizeof(PCB03_INDICES_ECLAIRAGE),
    .nb_del               = PCB03_NB_DEL,
};

const T07_Config *T07_ConfigDuNoeud(void)
{
#if (ESA_NOEUD == ESA_NOEUD_BAS)
    return &T07_CONFIG_BAS;
#elif (ESA_NOEUD == ESA_NOEUD_HAUT)
    return &T07_CONFIG_HAUT;
#elif (ESA_NOEUD == ESA_NOEUD_BORNE)
    return &T07_CONFIG_BORNE;
#else
#error "ESA_NOEUD inconnu (voir esa_noeud.h)"
#endif
}

/* ---- État du module ---- */
typedef T07_Couleur Couleur;

static const T07_Config         *s_cfg = NULL;
static T07_EnvoyerTrame          s_envoyer = NULL;
static RgbLedChain_HandleTypeDef s_chaine;              /* globale : lue par le DMA */
static T07_Place                 s_places[T07_MAX_PLACES_NOEUD];
static Couleur                   s_eclairage;
static Couleur                   s_ambiance;
static T07_Surcouche             s_surcouche = NULL;
static bool                      s_rpi_en_ligne = false;
static T07_Stats                 s_stats;

static Couleur s_image[RGB_LED_CHAIN_MAX_LEDS];         /* dernière image envoyée */
static bool    s_envoi_requis = true;                   /* image à (re)envoyer */

/* ---- Outils ---- */

static void repondre(uint16_t id, uint8_t seq, uint8_t valeur, uint8_t resultat)
{
    uint8_t data[DLC_REPONSE] = { seq, valeur, resultat };

    if (resultat == RESULTAT_APPLIQUE) { s_stats.appliquees++; }
    else                               { s_stats.refusees++; }

    if ((s_envoyer == NULL) || (id == 0u) || !s_envoyer(id, data, DLC_REPONSE))
    {
        s_stats.reponses_non_envoyees++;
    }
}

static bool place_du_noeud(uint8_t place)
{
    return (s_cfg->nb_places > 0u) &&
           (place >= s_cfg->premiere_place) &&
           (place < (uint8_t)(s_cfg->premiere_place + s_cfg->nb_places));
}

/* ---- Commandes ---- */

static void traiter_del_place(uint8_t dlc, const uint8_t *data)
{
    if (s_cfg->nb_places == 0u)
    {
        s_stats.ignorees++;              /* nœud sans témoins (HAUT) */
        return;
    }

    uint8_t seq   = (dlc >= 1u) ? data[0] : 0u;
    uint8_t place = (dlc >= 2u) ? data[1] : 0u;
    bool place_existe = (dlc >= 2u) && (place >= PLACE_MIN) && (place <= PLACE_MAX);

    if (place_existe && !place_du_noeud(place))
    {
        s_stats.ignorees++;              /* place de l'autre étage : l'autre nœud répond */
        return;
    }
    if (!place_existe || (dlc != DLC_DEL_PLACE_CMD) || (data[5] > MODE_MAX))
    {
        repondre(s_cfg->id_reponse_del, seq, place, RESULTAT_REFUSE);
        return;
    }

    T07_Place *p = &s_places[place - s_cfg->premiere_place];
    p->rouge = data[2];
    p->vert  = data[3];
    p->bleu  = data[4];
    p->mode  = data[5];
    p->etat  = T07_PLACE_VALIDE;
    s_envoi_requis = true;
    repondre(s_cfg->id_reponse_del, seq, place, RESULTAT_APPLIQUE);
}

static void traiter_eclairage(uint8_t dlc, const uint8_t *data)
{
    uint8_t seq    = (dlc >= 1u) ? data[0] : 0u;
    uint8_t niveau = (dlc >= 2u) ? data[1] : 0xFFu;
    bool niveau_existe = (dlc >= 2u) && (niveau <= NIVEAU_MAX);

    if (niveau_existe && (niveau != s_cfg->niveau_eclairage))
    {
        s_stats.ignorees++;              /* niveau d'un autre nœud */
        return;
    }
    if (!niveau_existe || (dlc != DLC_ECLAIRAGE_CMD) || (s_cfg->nb_eclairage == 0u))
    {
        repondre(s_cfg->id_reponse_eclairage, seq, niveau, RESULTAT_REFUSE);
        return;
    }

    s_eclairage.r = data[2];
    s_eclairage.v = data[3];
    s_eclairage.b = data[4];
    s_envoi_requis = true;
    repondre(s_cfg->id_reponse_eclairage, seq, niveau, RESULTAT_APPLIQUE);
}

/* ---- Interface ---- */

bool T07_Init(const T07_Config *config, SPI_HandleTypeDef *hspi, T07_EnvoyerTrame envoyer)
{
    if ((config == NULL) || (config->nb_places > T07_MAX_PLACES_NOEUD) ||
        ((config->nb_places > 0u) && (config->indice_place == NULL)) ||
        ((config->nb_eclairage > 0u) && (config->indices_eclairage == NULL)) ||
        ((config->nb_ambiance > 0u) && (config->indices_ambiance == NULL)) ||
        (config->nb_del > RGB_LED_CHAIN_MAX_LEDS))
    {
        return false;
    }
    for (uint8_t i = 0u; i < config->nb_places; i++)
    {
        if (config->indice_place[i] >= config->nb_del) { return false; }
    }
    for (uint8_t i = 0u; i < config->nb_eclairage; i++)
    {
        if (config->indices_eclairage[i] >= config->nb_del) { return false; }
    }
    for (uint8_t i = 0u; i < config->nb_ambiance; i++)
    {
        if (config->indices_ambiance[i] >= config->nb_del) { return false; }
    }
    if (RgbLedChain_Init(&s_chaine, hspi, config->nb_del) != HAL_OK)
    {
        return false;
    }

    s_cfg     = config;
    s_envoyer = envoyer;
    memset(s_places, 0, sizeof s_places);                 /* T07_PLACE_INITIALE : éteintes */
    if (config->nb_eclairage > 0u)
    {
        s_eclairage.r = T07_ECLAIRAGE_DEMARRAGE_R;
        s_eclairage.v = T07_ECLAIRAGE_DEMARRAGE_V;
        s_eclairage.b = T07_ECLAIRAGE_DEMARRAGE_B;
    }
    else
    {
        s_eclairage.r = 0u; s_eclairage.v = 0u; s_eclairage.b = 0u;
    }
    if (config->nb_ambiance > 0u)
    {
        s_ambiance = config->ambiance_demarrage;
    }
    else
    {
        s_ambiance.r = 0u; s_ambiance.v = 0u; s_ambiance.b = 0u;
    }
    s_rpi_en_ligne = false;
    memset(&s_stats, 0, sizeof s_stats);
    memset(s_image, 0, sizeof s_image);
    s_envoi_requis = true;                                /* 1er envoi au 1er appel de T07_Tache */
    return true;
}

void T07_TraiterTrame(uint16_t id, uint8_t dlc, const uint8_t *data)
{
    if ((s_cfg == NULL) || (data == NULL) || (dlc > 8u))
    {
        return;
    }
    if (id == CAN_ID_DEL_PLACE_CMD)
    {
        traiter_del_place(dlc, data);
    }
    else if (id == CAN_ID_ECLAIRAGE_CMD)
    {
        traiter_eclairage(dlc, data);
    }
}

void T07_SignalerRpi(bool en_ligne)
{
    if ((s_cfg != NULL) && s_rpi_en_ligne && !en_ligne)
    {
        /* Perte du RPi : les consignes ne sont plus garanties */
        for (uint8_t i = 0u; i < s_cfg->nb_places; i++)
        {
            s_places[i].etat = T07_PLACE_INCONNUE;
        }
        s_envoi_requis = true;
    }
    s_rpi_en_ligne = en_ligne;
}

void T07_Tache(uint32_t maintenant_ms)
{
    if (s_cfg == NULL)
    {
        return;
    }

    bool phase_allumee = ((maintenant_ms / T07_DEMI_PERIODE_CLIGNOTEMENT_MS) % 2u) == 0u;
    Couleur image[RGB_LED_CHAIN_MAX_LEDS];
    memset(image, 0, sizeof image);                       /* DEL non attribuées : éteintes */

    for (uint8_t i = 0u; i < s_cfg->nb_eclairage; i++)
    {
        image[s_cfg->indices_eclairage[i]] = s_eclairage;
    }
    for (uint8_t i = 0u; i < s_cfg->nb_ambiance; i++)
    {
        image[s_cfg->indices_ambiance[i]] = s_ambiance;
    }

    for (uint8_t i = 0u; i < s_cfg->nb_places; i++)
    {
        const T07_Place *p = &s_places[i];
        Couleur c = { 0u, 0u, 0u };

        if (p->etat == T07_PLACE_VALIDE)
        {
            if ((p->mode == 0u) || phase_allumee)
            {
                c.r = p->rouge; c.v = p->vert; c.b = p->bleu;
            }
        }
        else if (p->etat == T07_PLACE_INCONNUE)
        {
            if (phase_allumee)
            {
                c.r = T07_INCONNU_R; c.v = T07_INCONNU_V; c.b = T07_INCONNU_B;
            }
        }
        image[s_cfg->indice_place[i]] = c;
    }

    if (s_surcouche != NULL)
    {
        s_surcouche(image, s_cfg->nb_del, maintenant_ms);   /* animation (disco) */
    }

    if (!s_envoi_requis && (memcmp(image, s_image, s_cfg->nb_del * sizeof(Couleur)) == 0))
    {
        return;                                           /* rien n'a changé */
    }

    for (uint8_t i = 0u; i < s_cfg->nb_del; i++)
    {
        RgbLedChain_SetColor(&s_chaine, i, image[i].r, image[i].v, image[i].b, T07_LUMINOSITE_GLOBALE);
    }
    if (RgbLedChain_Show(&s_chaine) == HAL_OK)
    {
        memcpy(s_image, image, sizeof s_image);
        s_envoi_requis = false;
    }
    else
    {
        s_envoi_requis = true;                            /* SPI occupé : on réessaie au prochain appel */
    }
}

bool T07_LirePlace(uint8_t place, T07_Place *resultat)
{
    if ((s_cfg == NULL) || (resultat == NULL) || !place_du_noeud(place))
    {
        return false;
    }
    *resultat = s_places[place - s_cfg->premiere_place];
    return true;
}

void T07_LireEclairage(uint8_t *rouge, uint8_t *vert, uint8_t *bleu)
{
    if (rouge != NULL) { *rouge = s_eclairage.r; }
    if (vert  != NULL) { *vert  = s_eclairage.v; }
    if (bleu  != NULL) { *bleu  = s_eclairage.b; }
}

bool T07_RpiEnLigne(void)
{
    return s_rpi_en_ligne;
}

T07_Stats T07_LireStats(void)
{
    return s_stats;
}

const RgbLedChain_HandleTypeDef *T07_Chaine(void)
{
    return &s_chaine;
}

const T07_Config *T07_ConfigActive(void)
{
    return s_cfg;
}

bool T07_ReglerAmbiance(uint8_t r, uint8_t v, uint8_t b)
{
    if ((s_cfg == NULL) || (s_cfg->nb_ambiance == 0u))
    {
        return false;
    }
    s_ambiance.r = r; s_ambiance.v = v; s_ambiance.b = b;
    return true;
}

bool T07_LireAmbiance(uint8_t *r, uint8_t *v, uint8_t *b)
{
    if ((s_cfg == NULL) || (s_cfg->nb_ambiance == 0u) || (r == NULL) || (v == NULL) || (b == NULL))
    {
        return false;
    }
    *r = s_ambiance.r; *v = s_ambiance.v; *b = s_ambiance.b;
    return true;
}

void T07_DefinirSurcouche(T07_Surcouche surcouche)
{
    s_surcouche = surcouche;
    s_envoi_requis = true;                                /* réafficher tout de suite */
}
