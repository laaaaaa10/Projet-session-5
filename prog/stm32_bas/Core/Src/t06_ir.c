/*
 * t06_ir.c
 *
 *  Created on: 25 nov. 2026
 *      Author: William MacDonald (T06)
 *
 * Voir t06_ir.h.
 */

#include "t06_ir.h"
#include "esa_can_ids.h"
#include <stddef.h>
#include <string.h>

#define DLC_IR_CHANGEMENT    3u
#define DLC_IR_COMPLET       4u
#define DLC_IR_LECTURE       1u
#define CIBLE_BAS            1u
#define CIBLE_TOUS           0xFFu
#define DLC_SYNCHRO          1u
#define SYNCHRO_CAPTEURS     0x01u
#define SYNCHRO_TOUS         0x03u
#define ETAPE_AMBIANTE       (-1)

/* ---- Tables de câblage ----
 * Relevé sur le banc le 2026-11-25 (PCB-03 du bas, PCB-04 sur le MikroBus 1) :
 * les circuits IR tournent dans le sens INVERSE des DEL. En numérotation des DEL
 * (place 1 = D10 au-dessus de l'entrée, puis sens horaire vu de dessus) :
 *   circuit 0 → place 7, circuit 1 → place 6, …, circuit 6 → place 1 ;
 *   circuit 7 → passage du bras (entrée, entre les places 1 et 7).
 * Confirmé par : voitures sur les places 2 et 3 → circuits 5 et 4 ; diaphonie entre
 * circuits voisins (le circuit 7 est voisin des circuits 0 et 6).
 * Carte 1 (MikroBus 2, PCB-03 du milieu, places 8 à 14) : même câblage, confirmé
 * sur le banc le 2026-11-26 (deux nœuds, BAS et BORNE).
 * Indice CAN = place - 1. */
const uint8_t T06_INDICE[T06_NB_CARTES_MAX][T06_CIRCUITS_PAR_CARTE] =
{
    { 6u, 5u, 4u, 3u, 2u, 1u, 0u, T06_CIRCUIT_BRAS },
    { 13u, 12u, 11u, 10u, 9u, 8u, 7u, T06_CIRCUIT_BRAS },
};
const uint8_t T06_RECEPTEUR[T06_NB_CARTES_MAX][T06_CIRCUITS_PAR_CARTE] =
{
    { 0u, 1u, 2u, 3u, 4u, 5u, 6u, 7u },
    { 0u, 1u, 2u, 3u, 4u, 5u, 6u, 7u },
};

/* ---- État ---- */
typedef enum { PHASE_CHOISIR = 0, PHASE_ATTENDRE, PHASE_LIRE } Phase;

typedef struct
{
    T06_Etat confirme;
    T06_Etat candidat;
    uint8_t  compte;          /* lectures consécutives identiques au candidat */
    bool     parasite;        /* récepteur actif sans émetteur au dernier contrôle ambiant */
} Circuit;

static const T06_Carte  *s_cartes = NULL;
static uint8_t           s_nb_cartes = 0u;
static T06_EnvoyerTrame  s_envoyer = NULL;
static Circuit           s_circuits[T06_NB_CARTES_MAX][T06_CIRCUITS_PAR_CARTE];
static uint8_t           s_bruts[T06_NB_CARTES_MAX][T06_CIRCUITS_PAR_CARTE + 1u]; /* [0] = ambiant */

static uint8_t  s_carte;               /* carte en cours */
static int8_t   s_etape;               /* -1 = ambiant, puis 0 à 7 */
static Phase    s_phase;
static uint32_t s_t_choix;
static bool     s_erreur_balayage;     /* erreur de carte pendant le tour en cours */
static bool     s_erreur_dernier;      /* … pendant le dernier tour complet */

static uint32_t s_t_init;
static bool     s_premier_complet;     /* 1er 0x301 envoyé */
static uint32_t s_t_dernier_complet;
static bool     s_valide;
static uint8_t  s_compteur_evenements;
static T06_Stats s_stats;

/* ---- Outils ---- */

static bool circuit_lu(uint8_t carte, uint8_t circuit)
{
    return T06_INDICE[carte][circuit] != T06_CIRCUIT_INUTILISE;
}

static void envoyer(uint16_t id, const uint8_t *data, uint8_t dlc)
{
    if ((s_envoyer == NULL) || !s_envoyer(id, data, dlc))
    {
        s_stats.trames_non_envoyees++;
    }
}

static bool tous_publies_confirmes(void)
{
    for (uint8_t c = 0u; c < s_nb_cartes; c++)
    {
        for (uint8_t k = 0u; k < T06_CIRCUITS_PAR_CARTE; k++)
        {
            if ((T06_INDICE[c][k] < T06_NB_DETECTEURS) && (s_circuits[c][k].confirme == T06_INCONNU))
            {
                return false;
            }
        }
    }
    /* Indices attribués à une carte absente (banc avec une seule carte) : jamais confirmés */
    for (uint8_t c = s_nb_cartes; c < T06_NB_CARTES_MAX; c++)
    {
        for (uint8_t k = 0u; k < T06_CIRCUITS_PAR_CARTE; k++)
        {
            if (T06_INDICE[c][k] < T06_NB_DETECTEURS) { return false; }
        }
    }
    return true;
}

static bool parasite_publie(void)
{
    for (uint8_t c = 0u; c < s_nb_cartes; c++)
    {
        for (uint8_t k = 0u; k < T06_CIRCUITS_PAR_CARTE; k++)
        {
            if ((T06_INDICE[c][k] < T06_NB_DETECTEURS) && s_circuits[c][k].parasite) { return true; }
        }
    }
    return false;
}

static void envoyer_complet(void)
{
    uint8_t data[DLC_IR_COMPLET] = { 0u, 0u, s_compteur_evenements, s_valide ? 1u : 0u };

    for (uint8_t i = 0u; i < T06_NB_DETECTEURS; i++)
    {
        if (T06_LireDetecteur(i) == T06_PRESENCE)
        {
            data[i / 8u] |= (uint8_t)(1u << (i % 8u));
        }
    }
    envoyer(CAN_ID_IR_BAS_COMPLET, data, DLC_IR_COMPLET);
    s_stats.complets++;
}

/* Une lecture filtrée d'un circuit ; une confirmation après la première envoie 0x300. */
static void filtrer(uint8_t carte, uint8_t circuit, T06_Etat lu)
{
    Circuit *ci = &s_circuits[carte][circuit];

    if (lu == ci->confirme)
    {
        ci->candidat = lu;
        ci->compte = 0u;
        return;
    }
    if (lu == ci->candidat)
    {
        if (ci->compte < 255u) { ci->compte++; }
    }
    else
    {
        ci->candidat = lu;
        ci->compte = 1u;
    }
    if (ci->compte < T06_LECTURES_CONFIRMATION)
    {
        return;
    }

    bool premier = (ci->confirme == T06_INCONNU);
    ci->confirme = lu;
    ci->compte = 0u;

    uint8_t indice = T06_INDICE[carte][circuit];
    if (!premier && s_premier_complet && (indice < T06_NB_DETECTEURS))
    {
        s_compteur_evenements++;
        uint8_t data[DLC_IR_CHANGEMENT] = { indice, (lu == T06_PRESENCE) ? 1u : 0u, s_compteur_evenements };
        envoyer(CAN_ID_IR_BAS_CHANGEMENT, data, DLC_IR_CHANGEMENT);
        s_stats.changements++;
    }
}

/* Passe à l'étape suivante ; retourne true si un tour complet vient de se terminer. */
static bool avancer(void)
{
    s_phase = PHASE_CHOISIR;
    do
    {
        s_etape++;
        if (s_etape >= (int8_t)T06_CIRCUITS_PAR_CARTE)
        {
            /* Fin de la carte : éteindre son émetteur avant de passer à la suivante */
            if (!s_cartes[s_carte].choisir_emetteur(s_cartes[s_carte].ctx, -1))
            {
                s_stats.erreurs_carte++;
                s_erreur_balayage = true;
            }
            s_etape = ETAPE_AMBIANTE;
            s_carte++;
            if (s_carte >= s_nb_cartes)
            {
                s_carte = 0u;
                return true;
            }
            return false;
        }
    } while (!circuit_lu(s_carte, (uint8_t)s_etape));
    return false;
}

static void fin_de_tour(uint32_t maintenant_ms)
{
    s_stats.balayages++;
    s_erreur_dernier = s_erreur_balayage;
    s_erreur_balayage = false;

    bool valide = !s_erreur_dernier && !parasite_publie() && tous_publies_confirmes();
    bool changement_validite = (valide != s_valide);
    s_valide = valide;

    if (!s_premier_complet)
    {
        if (valide || ((maintenant_ms - s_t_init) >= T06_DELAI_MAX_VALIDATION_MS))
        {
            s_premier_complet = true;
            s_t_dernier_complet = maintenant_ms;
            envoyer_complet();
        }
    }
    else if (changement_validite)
    {
        s_t_dernier_complet = maintenant_ms;
        envoyer_complet();
    }
}

/* ---- Interface ---- */

bool T06_Init(const T06_Carte *cartes, uint8_t nb_cartes, T06_EnvoyerTrame envoyer_trame, uint32_t maintenant_ms)
{
    if ((cartes == NULL) || (nb_cartes == 0u) || (nb_cartes > T06_NB_CARTES_MAX))
    {
        return false;
    }
    for (uint8_t c = 0u; c < nb_cartes; c++)
    {
        if ((cartes[c].choisir_emetteur == NULL) || (cartes[c].lire_recepteurs == NULL)) { return false; }
        for (uint8_t k = 0u; k < T06_CIRCUITS_PAR_CARTE; k++)
        {
            if (T06_RECEPTEUR[c][k] >= T06_CIRCUITS_PAR_CARTE) { return false; }
        }
    }

    s_cartes = cartes;
    s_nb_cartes = nb_cartes;
    s_envoyer = envoyer_trame;
    memset(s_circuits, 0, sizeof s_circuits);      /* T06_INCONNU */
    memset(s_bruts, 0xFF, sizeof s_bruts);
    memset(&s_stats, 0, sizeof s_stats);

    s_carte = 0u;
    s_etape = ETAPE_AMBIANTE;
    s_phase = PHASE_CHOISIR;
    s_erreur_balayage = false;
    s_erreur_dernier = false;
    s_t_init = maintenant_ms;
    s_premier_complet = false;
    s_t_dernier_complet = maintenant_ms;
    s_valide = false;
    s_compteur_evenements = 0u;

    /* Tous les émetteurs éteints au départ */
    for (uint8_t c = 0u; c < nb_cartes; c++)
    {
        if (!cartes[c].choisir_emetteur(cartes[c].ctx, -1)) { s_stats.erreurs_carte++; }
    }
    return true;
}

void T06_Tache(uint32_t maintenant_ms)
{
    if (s_cartes == NULL)
    {
        return;
    }

    const T06_Carte *carte = &s_cartes[s_carte];

    switch (s_phase)
    {
        case PHASE_CHOISIR:
            if (carte->choisir_emetteur(carte->ctx, s_etape))
            {
                s_t_choix = maintenant_ms;
                s_phase = PHASE_ATTENDRE;
            }
            else
            {
                s_stats.erreurs_carte++;
                s_erreur_balayage = true;
                if (avancer()) { fin_de_tour(maintenant_ms); }
            }
            break;

        case PHASE_ATTENDRE:
            if ((maintenant_ms - s_t_choix) < T06_DELAI_STABILISATION_MS)
            {
                break;
            }
            s_phase = PHASE_LIRE;
            /* fall through */

        case PHASE_LIRE:
        {
            uint8_t niveaux = 0xFFu;
            if (!carte->lire_recepteurs(carte->ctx, &niveaux))
            {
                s_stats.erreurs_carte++;
                s_erreur_balayage = true;
            }
            else if (s_etape == ETAPE_AMBIANTE)
            {
                s_bruts[s_carte][0] = niveaux;
                for (uint8_t k = 0u; k < T06_CIRCUITS_PAR_CARTE; k++)
                {
                    if (!circuit_lu(s_carte, k)) { continue; }
                    bool actif = ((niveaux >> T06_RECEPTEUR[s_carte][k]) & 1u) == 0u;
                    Circuit *ci = &s_circuits[s_carte][k];
                    if (actif && !ci->parasite) { s_stats.parasites++; }
                    ci->parasite = actif;
                }
            }
            else
            {
                uint8_t k = (uint8_t)s_etape;
                s_bruts[s_carte][k + 1u] = niveaux;
                if (!s_circuits[s_carte][k].parasite)
                {
                    bool porteuse = ((niveaux >> T06_RECEPTEUR[s_carte][k]) & 1u) == 0u;
                    bool present = T06_PRESENCE_SI_PORTEUSE ? porteuse : !porteuse;
                    filtrer(s_carte, k, present ? T06_PRESENCE : T06_ABSENCE);
                }
            }
            if (avancer()) { fin_de_tour(maintenant_ms); }
            break;
        }

        default:
            s_phase = PHASE_CHOISIR;
            break;
    }

    /* 0x301 périodique */
    if (s_premier_complet && ((maintenant_ms - s_t_dernier_complet) >= T06_PERIODE_COMPLET_MS))
    {
        s_t_dernier_complet = maintenant_ms;
        envoyer_complet();
    }
}

void T06_TraiterTrame(uint16_t id, uint8_t dlc, const uint8_t *data)
{
    if ((s_cartes == NULL) || (data == NULL))
    {
        return;
    }
    if ((id == CAN_ID_IR_LECTURE_CMD) && (dlc == DLC_IR_LECTURE) &&
        ((data[0] == CIBLE_BAS) || (data[0] == CIBLE_TOUS)))
    {
        envoyer_complet();
    }
    else if ((id == CAN_ID_SYNCHRO_CMD) && (dlc == DLC_SYNCHRO) &&
             ((data[0] == SYNCHRO_CAPTEURS) || (data[0] == SYNCHRO_TOUS)))
    {
        envoyer_complet();                /* resynchronisation : aucun 0x300 artificiel */
    }
}

T06_Etat T06_LireDetecteur(uint8_t indice)
{
    for (uint8_t c = 0u; c < s_nb_cartes; c++)
    {
        for (uint8_t k = 0u; k < T06_CIRCUITS_PAR_CARTE; k++)
        {
            if (T06_INDICE[c][k] == indice) { return s_circuits[c][k].confirme; }
        }
    }
    return T06_INCONNU;
}

T06_Etat T06_LireCircuit(uint8_t carte, uint8_t circuit)
{
    if ((carte >= s_nb_cartes) || (circuit >= T06_CIRCUITS_PAR_CARTE)) { return T06_INCONNU; }
    return s_circuits[carte][circuit].confirme;
}

uint8_t T06_LireNiveauxBruts(uint8_t carte, int8_t circuit)
{
    if ((carte >= T06_NB_CARTES_MAX) || (circuit < ETAPE_AMBIANTE) || (circuit >= (int8_t)T06_CIRCUITS_PAR_CARTE))
    {
        return 0xFFu;
    }
    return s_bruts[carte][circuit + 1];
}

bool T06_CircuitParasite(uint8_t carte, uint8_t circuit)
{
    if ((carte >= s_nb_cartes) || (circuit >= T06_CIRCUITS_PAR_CARTE)) { return false; }
    return s_circuits[carte][circuit].parasite;
}

uint8_t T06_NbCartes(void)
{
    return s_nb_cartes;
}

bool T06_EstValide(void)
{
    return s_valide;
}

T06_Stats T06_LireStats(void)
{
    return s_stats;
}
