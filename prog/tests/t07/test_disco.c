/* Tests sur PC de l'animation disco (disco.c), qui passe par la surcouche de T07,
 * avec une chaîne simulée. */
#include <stdio.h>
#include <string.h>
#include "t07_del.h"
#include "disco.h"

static DMA_HandleTypeDef dma;
static SPI_HandleTypeDef spi = { &dma, HAL_SPI_STATE_READY, NULL, 0, 0, 0 };

/* ---- SPI simulé (DMA « instantané ») ---- */
HAL_SPI_StateTypeDef HAL_SPI_GetState(SPI_HandleTypeDef *hspi) { return hspi->State; }
HAL_StatusTypeDef HAL_SPI_Transmit_DMA(SPI_HandleTypeDef *hspi, uint8_t *pData, uint16_t Size)
{ hspi->last_data = pData; hspi->last_size = Size; hspi->dma_calls++; return HAL_OK; }
HAL_StatusTypeDef HAL_SPI_Transmit(SPI_HandleTypeDef *hspi, uint8_t *pData, uint16_t Size, uint32_t Timeout)
{ (void)Timeout; hspi->last_data = pData; hspi->last_size = Size; hspi->blocking_calls++; return HAL_OK; }

/* ---- Espion CAN : dernière réponse de T07 ---- */
static uint16_t dernier_id = 0;
static uint8_t  dernier_data[8];
static bool envoyer(uint16_t id, const uint8_t *d, uint8_t dlc)
{ dernier_id = id; memcpy(dernier_data, d, dlc); return true; }

static int echecs = 0, total = 0;
#define V(c, m) do { total++; if (!(c)) { echecs++; printf("ECHEC : %s (ligne %d)\n", m, __LINE__); } } while (0)

typedef struct { uint8_t r, v, b; } C;
static C del(uint8_t i)
{
    const uint8_t *f = T07_Chaine()->tx_frame + 4 + 4 * i;
    C c = { f[3], f[2], f[1] };
    return c;
}
static int egal(C c, uint8_t r, uint8_t v, uint8_t b) { return c.r == r && c.v == v && c.b == b; }
static int memes(C a, C b) { return a.r == b.r && a.v == b.v && a.b == b.b; }
static int maxc(C c) { int m = c.r; if (c.v > m) m = c.v; if (c.b > m) m = c.b; return m; }
/* Toutes les DEL de même parité (0 = dessous, 1 = parkings) ont cette couleur ? */
static int parite_est(int impair, uint8_t r, uint8_t v, uint8_t b)
{
    for (int k = impair; k < 15; k += 2) if (!egal(del((uint8_t)k), r, v, b)) return 0;
    return 1;
}
static void avancer(uint32_t de, uint32_t a) { for (uint32_t t = de; t < a; t++) T07_Tache(t); }

int main(void)
{
    V(T07_Init(&T07_CONFIG_HAUT, &spi, envoyer), "init HAUT");
    T07_Tache(0);
    V(parite_est(0, 64, 64, 64) && parite_est(1, 64, 0, 0), "HAUT au démarrage : dessous blanc, parkings rouges");
    V(!Disco_Choisir(4, DISCO_ZONE_TOUT, 60, 0), "mode 4 refusé");
    V(!Disco_Choisir(DISCO_ARC_EN_CIEL, 3, 60, 0), "zone 3 refusée");
    V(Disco_Mode() == DISCO_ARRET, "refus : la disco reste arrêtée");

    /* ===== 1 : arc-en-ciel, zone tout ===== */
    V(Disco_Choisir(DISCO_ARC_EN_CIEL, DISCO_ZONE_TOUT, 60, 0), "arc-en-ciel");
    int avant = spi.dma_calls;
    avancer(0, 1000);
    int images = spi.dma_calls - avant;
    printf("  arc-en-ciel : %d images en 1 s\n", images);
    V(images >= 38 && images <= 41, "40 images par seconde environ");
    int max = 0, differentes = 0;
    for (uint8_t i = 0; i < 15; i++) { if (maxc(del(i)) > max) max = maxc(del(i)); if (!memes(del(i), del(0))) differentes++; }
    V(max > 140 && max <= 153, "intensité 60 % : canal max ≤ 153");
    V(differentes >= 10, "arc-en-ciel : couleurs différentes autour de la carte");
    C a = del(0);
    avancer(1000, 1500);
    V(!memes(a, del(0)), "arc-en-ciel : les couleurs tournent");

    /* ===== 2 : stroboscope, zone tout ===== */
    V(Disco_Choisir(DISCO_STROBOSCOPE, DISCO_ZONE_TOUT, 100, 2000), "stroboscope");
    int allumes = 0, eteints = 0, blancs = 0, uniformes = 1;
    for (uint32_t t = 2000; t < 4000; t++)
    {
        T07_Tache(t);
        if ((t % 25) == 10)
        {
            C c0 = del(0);
            for (uint8_t i = 1; i < 15; i++) if (!memes(del(i), c0)) uniformes = 0;
            if (maxc(c0) == 0) eteints++; else allumes++;
            if (egal(c0, 255, 255, 255)) blancs++;
        }
    }
    printf("  stroboscope : %d images allumées, %d éteintes, %d blanches sur 2 s\n", allumes, eteints, blancs);
    V(uniformes, "stroboscope : toutes les DEL de la même couleur");
    V(allumes >= 12 && allumes <= 20 && eteints > allumes, "stroboscope : flashs courts (≈ 90 ms par 500 ms)");
    V(blancs >= 2 && blancs <= 6, "stroboscope : un flash blanc tous les 4 temps");

    /* ===== 3 : poursuite, zone tout ===== */
    V(Disco_Choisir(DISCO_POURSUITE, DISCO_ZONE_TOUT, 100, 5000), "poursuite");
    int tete_avant = -1, avances = 0, une_tete = 1;
    for (uint32_t t = 5000; t < 6000; t++)
    {
        T07_Tache(t);
        if ((t % 25) == 0)
        {
            int tete = -1, pleines = 0;
            for (uint8_t i = 0; i < 15; i++) if (maxc(del(i)) == 255) { tete = i; pleines++; }
            if (pleines != 1) une_tete = 0;
            if (tete >= 0 && tete != tete_avant) { if (tete_avant >= 0) avances++; tete_avant = tete; }
        }
    }
    printf("  poursuite : la tête a avancé %d fois en 1 s\n", avances);
    V(une_tete, "poursuite : une seule DEL à pleine intensité (la tête)");
    V(avances >= 14 && avances <= 17, "poursuite : une DEL toutes les 60 ms");

    /* ===== Zone parkings (HAUT : les 7 témoins du dessus) ===== */
    V(Disco_Choisir(DISCO_ARC_EN_CIEL, DISCO_ZONE_PARKINGS, 60, 6000) && Disco_Zone() == DISCO_ZONE_PARKINGS, "arc-en-ciel, zone parkings");
    avancer(6000, 6500);
    differentes = 0;
    for (int k = 3; k < 15; k += 2) if (!memes(del((uint8_t)k), del(1))) differentes++;
    V(parite_est(0, 64, 64, 64), "zone parkings : l'éclairage du dessous reste blanc");
    V(differentes >= 5 && !egal(del(1), 64, 0, 0), "zone parkings : arc-en-ciel sur les 7 parkings");
    dernier_id = 0;
    uint8_t d[5] = { 70, 2, 0, 0, 90 };
    T07_TraiterTrame(0x130, 5, d);
    V(dernier_id == 0x352 && dernier_data[2] == 1, "pendant la disco : la commande 0x130 niveau 2 est appliquée");
    avancer(6500, 6550);
    V(parite_est(0, 0, 0, 90), "zone parkings : la nouvelle couleur d'éclairage s'affiche dessous");

    V(Disco_Choisir(DISCO_POURSUITE, DISCO_ZONE_PARKINGS, 100, 7000), "poursuite, zone parkings");
    tete_avant = -1; avances = 0; une_tete = 1;
    int dessous_intact = 1;
    for (uint32_t t = 7000; t < 8000; t++)
    {
        T07_Tache(t);
        if ((t % 25) == 0)
        {
            int tete = -1, pleines = 0;
            for (int k = 1; k < 15; k += 2) if (maxc(del((uint8_t)k)) == 255) { tete = k; pleines++; }
            if (pleines != 1) une_tete = 0;
            if (!parite_est(0, 0, 0, 90)) dessous_intact = 0;
            if (tete >= 0 && tete != tete_avant) { if (tete_avant >= 0) avances++; tete_avant = tete; }
        }
    }
    printf("  poursuite sur les parkings : la tête a avancé %d fois en 1 s\n", avances);
    V(une_tete && dessous_intact, "poursuite, zone parkings : une tête sur les parkings, dessous intact");
    V(avances >= 6 && avances <= 8, "poursuite, zone parkings : un tour en ≈ 0,9 s (7 DEL)");

    /* ===== Zone dessous : les parkings gardent l'ambiance ===== */
    V(Disco_Choisir(DISCO_STROBOSCOPE, DISCO_ZONE_DESSOUS, 100, 8000), "stroboscope, zone dessous");
    int parkings_intacts = 1; uniformes = 1; allumes = 0;
    for (uint32_t t = 8000; t < 9000; t++)
    {
        T07_Tache(t);
        if ((t % 25) == 10)
        {
            if (!parite_est(1, 64, 0, 0)) parkings_intacts = 0;
            for (int k = 2; k < 15; k += 2) if (!memes(del((uint8_t)k), del(0))) uniformes = 0;
            if (maxc(del(0)) > 0) allumes++;
        }
    }
    V(parkings_intacts && uniformes && allumes >= 6, "zone dessous : flashs dessous, parkings rouges intacts");
    T07_ReglerAmbiance(0, 120, 0);
    avancer(9000, 9030);
    V(parite_est(1, 0, 120, 0), "zone dessous : un changement d'ambiance s'affiche sur les parkings");

    /* ===== Arrêt : image normale de T07 ===== */
    V(Disco_Choisir(DISCO_ARRET, DISCO_ZONE_TOUT, 0, 10000) && Disco_Mode() == DISCO_ARRET, "arrêt");
    T07_Tache(10000);
    V(parite_est(0, 0, 0, 90) && parite_est(1, 0, 120, 0), "arrêt : éclairage et ambiance réaffichés");
    avant = spi.dma_calls;
    avancer(10001, 10500);
    V(spi.dma_calls == avant, "arrêt : plus aucune image de la disco");

    /* ===== BORNE : zone parkings = les 7 places ===== */
    V(T07_Init(&T07_CONFIG_BORNE, &spi, envoyer), "init BORNE");
    V(Disco_Choisir(DISCO_ARC_EN_CIEL, DISCO_ZONE_PARKINGS, 60, 11000), "BORNE : arc-en-ciel, zone parkings");
    avancer(11000, 11300);
    differentes = 0;
    for (int k = 3; k < 15; k += 2) if (!memes(del((uint8_t)k), del(1))) differentes++;
    V(parite_est(0, 64, 64, 64) && differentes >= 5, "BORNE : arc-en-ciel sur les places, éclairage du niveau 1 intact");

    /* ===== BAS (maquette) : zone dessous sans éclairage → rien à animer ===== */
    V(T07_Init(&T07_CONFIG_BAS, &spi, envoyer), "init BAS");
    V(Disco_Choisir(DISCO_ARC_EN_CIEL, DISCO_ZONE_DESSOUS, 60, 12000), "BAS : zone dessous acceptée");
    T07_Tache(12000);
    avant = spi.dma_calls;
    avancer(12001, 12500);
    int noires = 1;
    for (uint8_t i = 0; i < 15; i++) if (maxc(del(i)) != 0) noires = 0;
    V(spi.dma_calls == avant && noires, "BAS sans éclairage : zone dessous vide, rien ne change");

    /* T07_Init pendant la disco : la disco continue avec la nouvelle configuration */
    V(T07_Init(&T07_CONFIG_HAUT, &spi, envoyer), "retour au HAUT");
    Disco_Choisir(DISCO_ARC_EN_CIEL, DISCO_ZONE_TOUT, 60, 13000);
    V(T07_Init(&T07_CONFIG_HAUT, &spi, envoyer), "re-init HAUT");
    avancer(13000, 13200);
    V(Disco_Mode() == DISCO_ARC_EN_CIEL && !egal(del(0), 64, 64, 64), "T07_Init : la disco continue");
    Disco_Choisir(DISCO_ARRET, DISCO_ZONE_TOUT, 0, 13200);

    printf("%d/%d vérifications réussies\n", total - echecs, total);
    return echecs != 0;
}
