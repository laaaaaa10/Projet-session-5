/*
 * Tests sur PC du module T06 (balayage IR, filtrage, trames 0x300/0x301/0x302).
 * Les cartes PCB-04 sont simulées : chaque circuit peut avoir un « véhicule »,
 * un parasite (récepteur actif sans émetteur) ou des erreurs I2C.
 * Compiler deux fois : -DT06_PRESENCE_SI_PORTEUSE=1 (réflexion) et =0 (faisceau coupé).
 */
#include <stdio.h>
#include <string.h>
#include "t06_ir.h"

/* ---- Cartes simulées ---- */
typedef struct
{
    int8_t  emetteur;              /* émetteur choisi, -1 = aucun */
    bool    vehicule[8];
    bool    parasite[8];
    bool    erreur;                /* échecs I2C */
    uint32_t choix;                /* nombre d'appels choisir_emetteur */
} CarteSim;

static CarteSim sim[2];
static int max_emetteurs_actifs = 0;

static bool sim_choisir(void *ctx, int8_t circuit)
{
    CarteSim *c = (CarteSim *)ctx;
    c->choix++;
    if (c->erreur) return false;
    c->emetteur = circuit;
    return true;
}
static bool sim_lire(void *ctx, uint8_t *niveaux)
{
    CarteSim *c = (CarteSim *)ctx;
    if (c->erreur) return false;
    int actifs = (sim[0].emetteur >= 0) + (sim[1].emetteur >= 0);
    if (actifs > max_emetteurs_actifs) max_emetteurs_actifs = actifs;
    uint8_t v = 0xFF;
    for (int r = 0; r < 8; r++)
    {
        bool porteuse = c->parasite[r];
        if (c->emetteur == r)
        {
            /* Réflexion : la porteuse revient si un véhicule est là. Barrière : elle passe s'il n'y en a pas. */
            porteuse |= T06_PRESENCE_SI_PORTEUSE ? c->vehicule[r] : !c->vehicule[r];
        }
        if (porteuse) v &= (uint8_t)~(1u << r);
    }
    *niveaux = v;
    return true;
}

/* Accès à la simulation par indice CAN, d'après les tables de câblage de t06_ir.c */
static bool *vehicule_de(uint8_t indice)
{
    for (int c = 0; c < 2; c++)
        for (int k = 0; k < 8; k++)
            if (T06_INDICE[c][k] == indice) return &sim[c].vehicule[T06_RECEPTEUR[c][k]];
    return NULL;
}
static bool *parasite_de(uint8_t indice)
{
    for (int c = 0; c < 2; c++)
        for (int k = 0; k < 8; k++)
            if (T06_INDICE[c][k] == indice) return &sim[c].parasite[T06_RECEPTEUR[c][k]];
    return NULL;
}
static int circuit_bras(int carte)
{
    for (int k = 0; k < 8; k++) if (T06_INDICE[carte][k] == T06_CIRCUIT_BRAS) return k;
    return -1;
}

static const T06_Carte cartes[2] =
{
    { sim_choisir, sim_lire, &sim[0] },
    { sim_choisir, sim_lire, &sim[1] },
};

/* ---- Espion CAN ---- */
typedef struct { uint16_t id; uint8_t dlc; uint8_t d[8]; uint32_t t; } Trame;
static Trame tr[256];
static int nb = 0;
static uint32_t maintenant = 0;
static bool espion(uint16_t id, const uint8_t *data, uint8_t dlc)
{
    if (nb < 256) { tr[nb].id = id; tr[nb].dlc = dlc; memcpy(tr[nb].d, data, dlc); tr[nb].t = maintenant; }
    nb++;
    return true;
}
static int compter(uint16_t id, int depuis) { int n = 0; for (int i = depuis; i < nb; i++) if (tr[i].id == id) n++; return n; }
static Trame *derniere(uint16_t id) { for (int i = nb - 1; i >= 0; i--) if (tr[i].id == id) return &tr[i]; return NULL; }

/* Fait tourner la boucle principale (2 appels par ms) jusqu'à t_fin */
static void tourner_jusqua(uint32_t t_fin)
{
    while (maintenant < t_fin) { T06_Tache(maintenant); T06_Tache(maintenant); maintenant++; }
}
/* Tourne jusqu'à une nouvelle trame id (ou délai max) ; retourne le délai écoulé, -1 si rien */
static int attendre_trame(uint16_t id, uint32_t max_ms)
{
    int avant = compter(id, 0);
    uint32_t t0 = maintenant;
    while (maintenant - t0 < max_ms)
    {
        T06_Tache(maintenant); T06_Tache(maintenant); maintenant++;
        if (compter(id, 0) > avant) return (int)(maintenant - t0);
    }
    return -1;
}

static int echecs = 0, total = 0;
#define VERIFIE(cond, msg) do { total++; if (!(cond)) { echecs++; printf("ECHEC : %s (ligne %d)\n", msg, __LINE__); } } while (0)

int main(void)
{
    printf("Mode : présence = %s\n", T06_PRESENCE_SI_PORTEUSE ? "porteuse reçue (réflexion)" : "faisceau coupé");
    for (int c = 0; c < 2; c++) sim[c].emetteur = 5;   /* état quelconque avant l'init */

    /* ===== Initialisation ===== */
    VERIFIE(!T06_Init(cartes, 0, espion, 0), "0 carte refusé");
    VERIFIE(!T06_Init(cartes, 3, espion, 0), "3 cartes refusé");
    VERIFIE(T06_Init(cartes, 2, espion, 0), "init 2 cartes");
    VERIFIE(sim[0].emetteur == -1 && sim[1].emetteur == -1, "init : émetteurs éteints");
    VERIFIE(!T06_EstValide(), "invalide avant le premier balayage");

    /* ===== Démarrage : aucun véhicule ===== */
    int dt = attendre_trame(0x301, 2000);
    VERIFIE(dt > 0 && dt <= 250, "1er 0x301 envoyé rapidement après validation");
    printf("  1er 0x301 après %d ms\n", dt);
    Trame *t = derniere(0x301);
    VERIFIE(t && t->dlc == 4 && t->d[0] == 0 && t->d[1] == 0 && t->d[2] == 0 && t->d[3] == 1, "0x301 [0, 0, 0, valide]");
    VERIFIE(compter(0x300, 0) == 0, "démarrage : aucun 0x300");
    VERIFIE(T06_EstValide(), "valide après démarrage");
    VERIFIE(T06_LireDetecteur(0) == T06_ABSENCE && T06_LireDetecteur(13) == T06_ABSENCE, "indices 0 et 13 : absence");
    VERIFIE(max_emetteurs_actifs <= 1, "jamais plus d'un émetteur allumé à la fois");

    T06_Stats s = T06_LireStats();
    uint32_t t0 = maintenant, b0 = s.balayages;
    tourner_jusqua(maintenant + 1000);
    s = T06_LireStats();
    printf("  %.1f ms par tour complet (2 cartes)\n", 1000.0 / (double)(s.balayages - b0));
    (void)t0;

    /* ===== Véhicule sur l'indice 3 ===== */
    *vehicule_de(3) = true;
    dt = attendre_trame(0x300, 1000);
    printf("  changement confirmé en %d ms\n", dt);
    VERIFIE(dt > 0 && dt <= 250, "changement confirmé en 250 ms ou moins");
    t = derniere(0x300);
    VERIFIE(t && t->dlc == 3 && t->d[0] == 3 && t->d[1] == 1 && t->d[2] == 1, "0x300 [3, présence, compteur 1]");
    VERIFIE(T06_LireDetecteur(3) == T06_PRESENCE, "indice 3 : présence");

    /* Pire cas : le changement arrive juste après la lecture du circuit */
    int pire = 0;
    for (int essai = 0; essai < 40; essai++)
    {
        tourner_jusqua(maintenant + 7);                 /* décaler la phase du balayage */
        *vehicule_de(3) = !*vehicule_de(3);
        dt = attendre_trame(0x300, 1000);
        if (dt > pire) pire = dt;
    }
    printf("  pire délai observé sur 40 changements : %d ms\n", pire);
    VERIFIE(pire > 0 && pire <= 250, "40 changements, tous confirmés en 250 ms ou moins");
    VERIFIE(T06_LireDetecteur(3) == (*vehicule_de(3) ? T06_PRESENCE : T06_ABSENCE), "après 40 bascules : état cohérent");
    if (*vehicule_de(3)) { *vehicule_de(3) = false; attendre_trame(0x300, 1000); }
    VERIFIE(T06_LireDetecteur(3) == T06_ABSENCE, "véhicule retiré : absence");

    /* ===== Parasite bref : pas de faux changement ===== */
    int avant = nb;
    *vehicule_de(5) = true;
    tourner_jusqua(maintenant + 30);                    /* < 2 tours : 1 ou 2 lectures seulement */
    *vehicule_de(5) = false;
    tourner_jusqua(maintenant + 500);
    VERIFIE(compter(0x300, avant) == 0, "impulsion de 30 ms : aucun 0x300 (filtrage)");

    /* ===== Indice 7 (carte 1) ===== */
    *vehicule_de(7) = true;
    dt = attendre_trame(0x300, 1000);
    t = derniere(0x300);
    VERIFIE(t && t->d[0] == 7 && t->d[1] == 1, "carte 1 → 0x300 indice 7");
    uint8_t compteur = t ? t->d[2] : 0;

    /* ===== Passage du bras : lu mais pas publié ===== */
    avant = nb;
    int kb = circuit_bras(0);
    VERIFIE(kb >= 0, "carte 0 : un circuit de passage du bras");
    sim[0].vehicule[T06_RECEPTEUR[0][kb]] = true;
    tourner_jusqua(maintenant + 500);
    VERIFIE(compter(0x300, avant) == 0, "passage du bras : aucun 0x300");
    VERIFIE(T06_LireCircuit(0, (uint8_t)kb) == T06_PRESENCE, "passage du bras lu (présence)");
    sim[0].vehicule[T06_RECEPTEUR[0][kb]] = false;
    tourner_jusqua(maintenant + 500);

    /* ===== Demande 0x302 ===== */
    uint8_t cible;
    avant = nb;
    cible = 1;    T06_TraiterTrame(0x302, 1, &cible);
    t = derniere(0x301);
    VERIFIE(compter(0x301, avant) == 1 && t->d[0] == 0x80 && t->d[1] == 0x00 && t->d[2] == compteur && t->d[3] == 1,
            "0x302 cible 1 → 0x301 [0x80 (indice 7), 0, compteur, valide]");
    avant = nb;
    cible = 0xFF; T06_TraiterTrame(0x302, 1, &cible);
    VERIFIE(compter(0x301, avant) == 1, "0x302 cible 0xFF → 0x301");
    avant = nb;
    cible = 2;    T06_TraiterTrame(0x302, 1, &cible);
    T06_TraiterTrame(0x302, 2, &cible);
    cible = 1;    T06_TraiterTrame(0x302, 0, &cible);
    T06_TraiterTrame(0x300, 1, &cible);
    VERIFIE(nb == avant, "0x302 cible 2, DLC incorrect ou autre trame : aucune réponse");
    uint8_t action;
    avant = nb;
    action = 0x01; T06_TraiterTrame(0x080, 1, &action);
    action = 0x03; T06_TraiterTrame(0x080, 1, &action);
    VERIFIE(compter(0x301, avant) == 2 && compter(0x300, avant) == 0, "SYNCHRO 0x01 et 0x03 → 0x301, aucun 0x300");
    avant = nb;
    action = 0x02; T06_TraiterTrame(0x080, 1, &action);
    VERIFIE(nb == avant, "SYNCHRO 0x02 (moteurs) : rien");

    /* Indice 13 = carte 1 circuit 6 → bit 5 de DB1 */
    *vehicule_de(13) = true;
    attendre_trame(0x300, 1000);
    cible = 1; T06_TraiterTrame(0x302, 1, &cible);
    t = derniere(0x301);
    VERIFIE(t && t->d[0] == 0x80 && t->d[1] == 0x20, "indice 13 → bit 5 de DB1");
    *vehicule_de(13) = false;
    attendre_trame(0x300, 1000);

    /* ===== Parasite (récepteur actif sans émetteur) ===== */
    *parasite_de(9) = true;
    dt = attendre_trame(0x301, 500);
    t = derniere(0x301);
    VERIFIE(dt > 0 && t->d[3] == 0, "parasite : 0x301 envoyé avec validité 0");
    VERIFIE(!T06_EstValide(), "parasite : invalide");
    VERIFIE(T06_LireDetecteur(9) == T06_ABSENCE, "parasite : l'indice 9 garde son dernier état");
    avant = nb;
    tourner_jusqua(maintenant + 500);
    VERIFIE(compter(0x300, avant) == 0, "parasite : aucun faux 0x300 sur l'indice 9");
    *parasite_de(9) = false;
    dt = attendre_trame(0x301, 500);
    t = derniere(0x301);
    VERIFIE(dt > 0 && t->d[3] == 1, "parasite disparu : 0x301 avec validité 1");
    VERIFIE(T06_LireStats().parasites >= 1, "parasite compté");

    /* ===== Erreur I2C sur la carte 0 ===== */
    sim[0].erreur = true;
    dt = attendre_trame(0x301, 500);
    t = derniere(0x301);
    VERIFIE(dt > 0 && t->d[3] == 0, "erreur I2C : 0x301 avec validité 0");
    VERIFIE(T06_LireStats().erreurs_carte > 0, "erreurs comptées");
    VERIFIE(T06_LireDetecteur(7) == T06_PRESENCE, "la carte 1 continue d'être lue");
    sim[0].erreur = false;
    dt = attendre_trame(0x301, 500);
    VERIFIE(dt > 0 && derniere(0x301)->d[3] == 1, "carte 0 revenue : validité 1");

    /* ===== 0x301 périodique ===== */
    avant = nb;
    tourner_jusqua(maintenant + 125000);
    int n301 = compter(0x301, avant);
    VERIFIE(n301 == 2, "125 s sans changement : deux 0x301 périodiques");
    VERIFIE(compter(0x300, avant) == 0, "125 s sans changement : aucun 0x300");

    /* ===== Banc avec une seule carte ===== */
    nb = 0; maintenant = 0;
    memset(sim, 0, sizeof sim);
    VERIFIE(T06_Init(cartes, 1, espion, 0), "init 1 carte");
    dt = attendre_trame(0x301, 2000);
    t = derniere(0x301);
    VERIFIE(dt >= 1000 && dt <= 1100 && t->d[3] == 0, "1 carte : 1er 0x301 après le délai max, validité 0 (indices 7-13 inconnus)");
    VERIFIE(sim[1].choix == 0, "1 carte : la carte 1 n'est jamais utilisée");
    *vehicule_de(0) = true;
    dt = attendre_trame(0x300, 1000);
    t = derniere(0x300);
    VERIFIE(dt > 0 && dt <= 250 && t->d[0] == 0 && t->d[1] == 1, "1 carte : changements publiés quand même");

    printf("%d/%d vérifications réussies\n", total - echecs, total);
    return echecs == 0 ? 0 : 1;
}
