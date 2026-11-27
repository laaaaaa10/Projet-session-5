/*
 * essai_t06.c
 *
 *  Created on: 25 nov. 2026
 *      Author: William MacDonald (T06)
 *
 * Voir essai_t06.h.
 */

#include "essai_t06.h"
#include "console.h"
#include "esa_can_ids.h"
#include "t06_ir.h"
#include "disco.h"
#include "t07_del.h"     /* couleurs de démarrage (état initial de demo on) */
#include <stdlib.h>
#include <string.h>

#define DEMO_NB_PLACES   14u

static bool     s_demo = false;
static uint16_t s_demo_a_envoyer = 0u;      /* bit p = place p+1 à envoyer */
static uint16_t s_demo_presence = 0u;       /* bit p = place p+1 occupée */
static uint8_t  s_demo_seq = 0u;
static bool     s_demo_eteindre = false;    /* demo off : éteindre les témoins */
/* Éclairage remis par demo on (état initial) ou éteint par demo off, une trame à la fois :
 * bit n = 0x130 du niveau n (0 à 2), 0x08 = arrêt de la disco, 0x10 = ambiance des parkings du HAUT */
#define DEMO_ECL_ESPACEMENT_MS 2u
static uint8_t  s_demo_ecl_a_envoyer = 0u;
static bool     s_demo_ecl_initial = false;   /* true : couleurs de démarrage, false : éteint */
static uint32_t s_t_demo_ecl = 0u;

/* État logique choisi par le « faux RPi » pour chaque place */
typedef enum { DEMO_NORMAL = 0, DEMO_RESERVEE, DEMO_REPARATION } DemoMode;
static DemoMode s_demo_mode[DEMO_NB_PLACES];
/* Intensité de chaque place en % (demo intensite) : appliquée aux couleurs du faux RPi */
static uint8_t  s_demo_intensite[DEMO_NB_PLACES] = { 100u, 100u, 100u, 100u, 100u, 100u, 100u,
                                                     100u, 100u, 100u, 100u, 100u, 100u, 100u };

static const char *nom_etat(T06_Etat e)
{
    switch (e)
    {
        case T06_PRESENCE: return "PRESENCE";
        case T06_ABSENCE:  return "absence ";
        default:           return "inconnu ";
    }
}

const char *EssaiT06_NomTrame(uint16_t id)
{
    switch (id)
    {
        case CAN_ID_IR_BAS_CHANGEMENT: return "IR_BAS_CHANGEMENT";
        case CAN_ID_IR_BAS_COMPLET:    return "IR_BAS_COMPLET";
        case CAN_ID_IR_LECTURE_CMD:    return "IR_LECTURE_CMD";
        case CAN_ID_SYNCHRO_CMD:       return "SYNCHRO_CMD";
        default:                       return "";
    }
}

void EssaiT06_Aide(void)
{
    Console_Ecrire("  ir                               T06 : etat des 16 circuits\r\n"
                   "  ir brut                          T06 : lectures brutes (# = porteuse recue)\r\n"
                   "  ir lire                          T06 : demande 0x302, reponse 0x301\r\n"
                   "  demo on | demo off               faux RPi : libre vert, occupee rouge\r\n"
                   "                                   (on : etat initial comme apres RESET ; off : tout eteint)\r\n"
                   "  demo reserve <place>             place reservee : bleu (rouge si occupee)\r\n"
                   "  demo reparation <place>          place en reparation : jaune\r\n"
                   "  demo normal <place>              retour a vert / rouge selon l'IR\r\n"
                   "  demo intensite <place|tous> <%>  intensite des temoins, ex. demo intensite tous 20\r\n"
                   "  demo etat                        etat logique des 14 places\r\n");
}

static const char *nom_mode(DemoMode m)
{
    switch (m)
    {
        case DEMO_RESERVEE:   return "reservee";
        case DEMO_REPARATION: return "reparation";
        default:              return "normale";
    }
}

/* Couleur choisie par le faux RPi (couleurs indicatives du protocole, réparation en jaune fixe) */
static void couleur_place(uint8_t i, uint8_t *r, uint8_t *v, uint8_t *b)
{
    bool occupee = (s_demo_presence & (1u << i)) != 0u;
    *r = 0u; *v = 0u; *b = 0u;
    switch (s_demo_mode[i])
    {
        case DEMO_REPARATION: *r = 255u; *v = 255u;              break;  /* jaune */
        case DEMO_RESERVEE:   if (occupee) { *r = 255u; } else { *b = 255u; } break;
        default:              if (occupee) { *r = 255u; } else { *v = 255u; } break;
    }
    uint32_t pct = s_demo_intensite[i];
    *r = (uint8_t)(((uint32_t)*r * pct + 50u) / 100u);
    *v = (uint8_t)(((uint32_t)*v * pct + 50u) / 100u);
    *b = (uint8_t)(((uint32_t)*b * pct + 50u) / 100u);
}

static void cmd_ir_etat(void)
{
    T06_Stats s = T06_LireStats();

    Console_Printf("IR : %s | %lu tours, %lu erreurs I2C, %lu parasites | %lu x 0x300, %lu x 0x301\r\n",
                   T06_EstValide() ? "VALIDE" : "NON FIABLE",
                   (unsigned long)s.balayages, (unsigned long)s.erreurs_carte, (unsigned long)s.parasites,
                   (unsigned long)s.changements, (unsigned long)s.complets);
    for (uint8_t c = 0u; c < T06_NbCartes(); c++)
    {
        Console_Printf(" carte %u (MikroBus %u)\r\n", c, c + 1u);
        for (uint8_t k = 0u; k < T06_CIRCUITS_PAR_CARTE; k++)
        {
            uint8_t indice = T06_INDICE[c][k];
            if (indice == T06_CIRCUIT_INUTILISE) { continue; }
            if (indice == T06_CIRCUIT_BRAS)
            {
                Console_Printf("  circuit %u -> passage du bras     : %s%s\r\n", k,
                               nom_etat(T06_LireCircuit(c, k)), T06_CircuitParasite(c, k) ? "  PARASITE" : "");
            }
            else
            {
                Console_Printf("  circuit %u -> indice %2u (place %2u) : %s%s\r\n", k, indice, indice + 1u,
                               nom_etat(T06_LireCircuit(c, k)), T06_CircuitParasite(c, k) ? "  PARASITE" : "");
            }
        }
    }
}

static void afficher_ligne_brute(const char *titre, uint8_t niveaux)
{
    char texte[9];
    for (uint8_t r = 0u; r < 8u; r++)
    {
        texte[r] = (((niveaux >> r) & 1u) == 0u) ? '#' : '.';
    }
    texte[8] = '\0';
    Console_Printf("    %-16s %s\r\n", titre, texte);
}

static void cmd_ir_brut(void)
{
    Console_Ecrire("# = porteuse recue par ce recepteur (sortie basse)\r\n");
#if T06_PRESENCE_SI_PORTEUSE
    Console_Ecrire("Sens : vehicule = porteuse recue (reflexion) : '#' sur la diagonale = presence\r\n");
#else
    Console_Ecrire("Sens : vehicule = faisceau coupe : '#' sur la diagonale = place vide\r\n");
#endif
    for (uint8_t c = 0u; c < T06_NbCartes(); c++)
    {
        Console_Printf(" carte %u (MikroBus %u)   recepteurs 01234567\r\n", c, c + 1u);
        afficher_ligne_brute("aucun emetteur", T06_LireNiveauxBruts(c, -1));
        for (int8_t e = 0; e < (int8_t)T06_CIRCUITS_PAR_CARTE; e++)
        {
            char titre[17];
            titre[0] = '\0';
            strcat(titre, "emetteur ");
            titre[9] = (char)('0' + e);
            titre[10] = '\0';
            afficher_ligne_brute(titre, T06_LireNiveauxBruts(c, e));
        }
    }
}

static void envoyer_lecture(void)
{
    uint8_t cible = 1u;
    if (!CanEsa_Envoyer(CAN_ID_IR_LECTURE_CMD, &cible, 1u))
    {
        Console_Ecrire("   ERREUR : aucune boite d'emission CAN libre\r\n");
    }
}

bool EssaiT06_Executer(char **j, uint8_t n)
{
    if (strcmp(j[0], "ir") == 0)
    {
        if (n == 1u)                                   { cmd_ir_etat(); }
        else if ((n == 2u) && (strcmp(j[1], "brut") == 0)) { cmd_ir_brut(); }
        else if ((n == 2u) && (strcmp(j[1], "lire") == 0))
        {
            Console_Ecrire("-> 0x302 IR_LECTURE_CMD [1]\r\n");
            envoyer_lecture();
        }
        else { Console_Ecrire("Usage : ir | ir brut | ir lire\r\n"); }
        return true;
    }
    if ((strcmp(j[0], "demo") == 0) && (n >= 2u) && (strcmp(j[1], "intensite") == 0))
    {
        bool tous = (n == 4u) && (strcmp(j[2], "tous") == 0);
        unsigned long place = (n == 4u) ? strtoul(j[2], NULL, 0) : 0u;
        if ((n != 4u) || (j[3][0] < '0') || (j[3][0] > '9') || (!tous && ((place < 1u) || (place > DEMO_NB_PLACES))))
        {
            Console_Ecrire("Usage : demo intensite <place 1-14 | tous> <0-100 %>\r\n");
            return true;
        }
        unsigned long pct = strtoul(j[3], NULL, 0);
        if (pct > 100u) { pct = 100u; }
        for (uint8_t i = 0u; i < DEMO_NB_PLACES; i++)
        {
            if (tous || (i == (place - 1u)))
            {
                s_demo_intensite[i] = (uint8_t)pct;
                if (s_demo) { s_demo_a_envoyer |= (uint16_t)(1u << i); }
            }
        }
        if (tous) { Console_Printf("Places 1 a 14 : intensite %lu %%", pct); }
        else      { Console_Printf("Place %lu : intensite %lu %%", place, pct); }
        Console_Ecrire(s_demo ? "\r\n" : " (demo inactive : taper demo on)\r\n");
        return true;
    }
    if ((strcmp(j[0], "demo") == 0) && (n == 3u))
    {
        DemoMode mode;
        if (strcmp(j[1], "reserve") == 0)         { mode = DEMO_RESERVEE; }
        else if (strcmp(j[1], "reparation") == 0) { mode = DEMO_REPARATION; }
        else if (strcmp(j[1], "normal") == 0)     { mode = DEMO_NORMAL; }
        else { Console_Ecrire("Usage : demo reserve | reparation | normal <place 1-14>\r\n"); return true; }
        unsigned long place = strtoul(j[2], NULL, 0);
        if ((place < 1u) || (place > DEMO_NB_PLACES))
        {
            Console_Ecrire("Place 1 a 14\r\n");
            return true;
        }
        s_demo_mode[place - 1u] = mode;
        Console_Printf("Place %lu : %s%s\r\n", place, nom_mode(mode), s_demo ? "" : " (demo inactive : taper demo on)");
        if (s_demo) { s_demo_a_envoyer |= (uint16_t)(1u << (place - 1u)); }
        return true;
    }
    if ((strcmp(j[0], "demo") == 0) && (n == 2u) && (strcmp(j[1], "etat") == 0))
    {
        Console_Printf("Demo : %s\r\n", s_demo ? "active" : "inactive");
        for (uint8_t i = 0u; i < DEMO_NB_PLACES; i++)
        {
            Console_Printf("  place %2u : %-10s %-8s %3u %%\r\n", i + 1u, nom_mode(s_demo_mode[i]),
                           ((s_demo_presence & (1u << i)) != 0u) ? "occupee" : "libre", s_demo_intensite[i]);
        }
        return true;
    }
    if ((strcmp(j[0], "demo") == 0) && (n == 2u))
    {
        bool etait_active = s_demo;
        s_demo = (strcmp(j[1], "on") == 0);
        s_demo_a_envoyer = 0u;
        s_demo_eteindre = false;
        s_demo_ecl_a_envoyer = 0u;
        Console_Printf("Demo T06 -> T07 (faux RPi) : %s\r\n", s_demo ? "oui" : "non");
        if (!s_demo && etait_active)
        {
            /* Les STM32 gardent la dernière consigne : le faux RPi éteint donc les témoins
             * et l'éclairage en partant */
            s_demo_eteindre = true;
            s_demo_a_envoyer = (uint16_t)((1u << DEMO_NB_PLACES) - 1u);
            s_demo_ecl_a_envoyer = 0x1Fu;               /* niveaux 0 à 2 + arrêt de la disco + ambiance */
            s_demo_ecl_initial = false;
        }
        if (s_demo)
        {
            /* État initial, comme après un RESET : disco arrêtée, éclairage blanc, parkings du
             * haut rouges, places en mode normal à 100 % */
            for (uint8_t i = 0u; i < DEMO_NB_PLACES; i++)
            {
                s_demo_mode[i] = DEMO_NORMAL;
                s_demo_intensite[i] = 100u;
            }
            s_demo_ecl_a_envoyer = 0x1Fu;
            s_demo_ecl_initial = true;
            Console_Ecrire("   Etat initial : disco arretee, eclairage blanc, parkings du haut rouges, places normales a 100 %\r\n");
            if (!CanEsa_EnLoopback() && !CanEsa_EchoLocal())
            {
                Console_Ecrire("   Attention : ni loopback ni echo local, le STM32 ne recoit pas ses propres 0x300.\r\n");
            }
            envoyer_lecture();                       /* état complet → couleur de toutes les places */
        }
        return true;
    }
    return false;
}

void EssaiT06_ObserverTrame(const TrameCan *t)
{
    if ((t->id == CAN_ID_IR_BAS_CHANGEMENT) && (t->dlc == 3u))
    {
        uint8_t indice = t->data[0];
        Console_Printf("<- 0x300 IR_BAS_CHANGEMENT : indice %u (place %u) -> %s (evenement %u)\r\n",
                       indice, indice + 1u, (t->data[1] == 1u) ? "PRESENCE" : "absence", t->data[2]);
        if (s_demo && (indice < DEMO_NB_PLACES))
        {
            if (t->data[1] == 1u) { s_demo_presence |= (uint16_t)(1u << indice); }
            else                  { s_demo_presence &= (uint16_t)~(1u << indice); }
            s_demo_a_envoyer |= (uint16_t)(1u << indice);
        }
    }
    else if ((t->id == CAN_ID_IR_BAS_COMPLET) && (t->dlc == 4u))
    {
        uint16_t masque = (uint16_t)(t->data[0] | ((uint16_t)(t->data[1] & 0x3Fu) << 8));
        char places[DEMO_NB_PLACES + 2u];
        uint8_t p = 0u;
        for (uint8_t i = 0u; i < DEMO_NB_PLACES; i++)
        {
            if (i == 7u) { places[p++] = ' '; }
            places[p++] = ((masque >> i) & 1u) ? 'X' : '.';
        }
        places[p] = '\0';
        Console_Printf("<- 0x301 IR_BAS_COMPLET : places 1-14 [%s] (X = presence), evenements %u, %s\r\n",
                       places, t->data[2], (t->data[3] == 1u) ? "VALIDE" : "NON FIABLE");
        if (s_demo)
        {
            s_demo_presence = masque;
            s_demo_a_envoyer = (uint16_t)((1u << DEMO_NB_PLACES) - 1u);
        }
    }
}

void EssaiT06_RafraichirDemo(void)
{
    if (s_demo)
    {
        s_demo_a_envoyer = (uint16_t)((1u << DEMO_NB_PLACES) - 1u);
    }
}

void EssaiT06_Tache(uint32_t maintenant_ms)
{
    /* Une trame à la fois : les 3 boîtes d'émission CAN ne suffisent pas pour 14 d'un coup */
    if ((s_demo || s_demo_eteindre) && (s_demo_a_envoyer != 0u))
    {
        for (uint8_t i = 0u; i < DEMO_NB_PLACES; i++)
        {
            if ((s_demo_a_envoyer & (1u << i)) == 0u) { continue; }
            uint8_t r, v, b;
            couleur_place(i, &r, &v, &b);
            if (s_demo_eteindre) { r = 0u; v = 0u; b = 0u; }
            uint8_t d[6] = { s_demo_seq, (uint8_t)(i + 1u), r, v, b, 0u };   /* fixe */
            if (CanEsa_Envoyer(CAN_ID_DEL_PLACE_CMD, d, sizeof d))
            {
                s_demo_seq++;
                s_demo_a_envoyer &= (uint16_t)~(1u << i);
            }
            return;
        }
    }
    s_demo_a_envoyer = s_demo ? s_demo_a_envoyer : 0u;
    s_demo_eteindre = false;

    /* demo on / demo off : disco, ambiance puis éclairage des niveaux 0 à 2, une trame toutes les 2 ms
     * (chaque nœud ignore les niveaux qui ne sont pas les siens) */
    if ((s_demo_ecl_a_envoyer == 0u) || ((maintenant_ms - s_t_demo_ecl) < DEMO_ECL_ESPACEMENT_MS))
    {
        return;
    }
    if ((s_demo_ecl_a_envoyer & 0x08u) != 0u)
    {
        uint8_t d[3] = { DISCO_ARRET, DISCO_CIBLE_TOUS, 0u };
        if (CanEsa_Envoyer(CAN_ID_ESSAI_DISCO, d, sizeof d))
        {
            s_demo_ecl_a_envoyer &= (uint8_t)~0x08u;
            s_t_demo_ecl = maintenant_ms;
        }
        return;
    }
    if ((s_demo_ecl_a_envoyer & 0x10u) != 0u)
    {
        uint8_t d[3] = { 0u, 0u, 0u };
        if (s_demo_ecl_initial)
        {
            d[0] = T07_AMBIANCE_DEMARRAGE_R; d[1] = T07_AMBIANCE_DEMARRAGE_V; d[2] = T07_AMBIANCE_DEMARRAGE_B;
        }
        if (CanEsa_Envoyer(CAN_ID_ESSAI_AMBIANCE, d, sizeof d))
        {
            s_demo_ecl_a_envoyer &= (uint8_t)~0x10u;
            s_t_demo_ecl = maintenant_ms;
        }
        return;
    }
    for (uint8_t niveau = 0u; niveau < 3u; niveau++)
    {
        if ((s_demo_ecl_a_envoyer & (1u << niveau)) == 0u) { continue; }
        uint8_t d[5] = { s_demo_seq, niveau, 0u, 0u, 0u };
        if (s_demo_ecl_initial)
        {
            d[2] = T07_ECLAIRAGE_DEMARRAGE_R; d[3] = T07_ECLAIRAGE_DEMARRAGE_V; d[4] = T07_ECLAIRAGE_DEMARRAGE_B;
        }
        if (CanEsa_Envoyer(CAN_ID_ECLAIRAGE_CMD, d, sizeof d))
        {
            s_demo_seq++;
            s_demo_ecl_a_envoyer &= (uint8_t)~(1u << niveau);
            s_t_demo_ecl = maintenant_ms;
        }
        return;
    }
}
