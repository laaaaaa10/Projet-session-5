/*
 * Tests sur PC du pilote rgb_led_chain (format de trame, validation, DMA occupé).
 * Compilation : voir le Makefile de ce dossier
 * (make) ; aucun matériel nécessaire.
 */
#include <stdio.h>
#include <string.h>
#include "rgb_led_chain.h"

/* ---- Faux HAL ---- */
HAL_SPI_StateTypeDef HAL_SPI_GetState(SPI_HandleTypeDef *hspi) { return hspi->State; }

HAL_StatusTypeDef HAL_SPI_Transmit_DMA(SPI_HandleTypeDef *hspi, uint8_t *pData, uint16_t Size)
{
    hspi->last_data = pData; hspi->last_size = Size; hspi->dma_calls++;
    hspi->State = HAL_SPI_STATE_BUSY_TX;          /* reste occupé jusqu'à la « fin du DMA » */
    return HAL_OK;
}

HAL_StatusTypeDef HAL_SPI_Transmit(SPI_HandleTypeDef *hspi, uint8_t *pData, uint16_t Size, uint32_t Timeout)
{
    (void)Timeout;
    hspi->last_data = pData; hspi->last_size = Size; hspi->blocking_calls++;
    return HAL_OK;
}

/* ---- Mini cadre de test ---- */
static int echecs = 0, total = 0;
#define VERIFIE(cond, msg) do { total++; if (!(cond)) { echecs++; printf("ECHEC : %s (ligne %d)\n", msg, __LINE__); } } while (0)

static RgbLedChain_HandleTypeDef chaine;   /* globale, comme sur la cible */

int main(void)
{
    DMA_HandleTypeDef dma;
    SPI_HandleTypeDef spi = { .hdmatx = &dma, .State = HAL_SPI_STATE_READY };

    /* Init : paramètres invalides */
    VERIFIE(RgbLedChain_Init(NULL, &spi, 15) == HAL_ERROR, "dev nul refusé");
    VERIFIE(RgbLedChain_Init(&chaine, NULL, 15) == HAL_ERROR, "SPI nul refusé");
    VERIFIE(RgbLedChain_Init(&chaine, &spi, 0) == HAL_ERROR, "0 DEL refusé");
    VERIFIE(RgbLedChain_Init(&chaine, &spi, RGB_LED_CHAIN_MAX_LEDS + 1) == HAL_ERROR, "trop de DEL refusé");

    /* Init : chaîne du PCB-03 (15 DEL) */
    VERIFIE(RgbLedChain_Init(&chaine, &spi, 15) == HAL_OK, "init 15 DEL");
    VERIFIE(chaine.frame_size == 4 + 15 * 4 + 4, "taille de trame 68 octets");
    const uint8_t zeros[4] = {0, 0, 0, 0}, uns[4] = {0xFF, 0xFF, 0xFF, 0xFF}, eteinte[4] = {0xE0, 0, 0, 0};
    VERIFIE(memcmp(chaine.frame, zeros, 4) == 0, "début = 4 x 0x00");
    VERIFIE(memcmp(&chaine.frame[64], uns, 4) == 0, "fin = 4 x 0xFF après la 15e DEL");
    int toutes_eteintes = 1;
    for (int i = 0; i < 15; i++) { if (memcmp(&chaine.frame[4 + 4 * i], eteinte, 4) != 0) toutes_eteintes = 0; }
    VERIFIE(toutes_eteintes, "15 DEL éteintes après init (E0 00 00 00)");

    /* SetColor : orange (255,165,0) luminosité 31 sur la DEL d'indice 3 */
    VERIFIE(RgbLedChain_SetColor(&chaine, 3, 255, 165, 0, 31) == HAL_OK, "SetColor valide");
    const uint8_t orange[4] = {0xFF, 0x00, 0xA5, 0xFF};      /* E0|31, bleu, vert, rouge */
    VERIFIE(memcmp(&chaine.frame[4 + 12], orange, 4) == 0, "octets DEL 3 = FF 00 A5 FF (ordre B, G, R)");
    VERIFIE(memcmp(&chaine.frame[4 + 8], eteinte, 4) == 0 && memcmp(&chaine.frame[4 + 16], eteinte, 4) == 0,
            "DEL voisines 2 et 4 inchangées");

    /* SetColor : rouge pur luminosité 8 sur la dernière DEL */
    VERIFIE(RgbLedChain_SetColor(&chaine, 14, 255, 0, 0, 8) == HAL_OK, "SetColor dernière DEL");
    const uint8_t rouge8[4] = {0xE8, 0x00, 0x00, 0xFF};
    VERIFIE(memcmp(&chaine.frame[4 + 56], rouge8, 4) == 0, "DEL 14 = E8 00 00 FF");
    VERIFIE(memcmp(&chaine.frame[64], uns, 4) == 0, "fin de trame intacte");

    /* SetColor : paramètres invalides, image inchangée */
    uint8_t avant[RGB_LED_CHAIN_FRAME_MAX_BYTES];
    memcpy(avant, chaine.frame, sizeof avant);
    VERIFIE(RgbLedChain_SetColor(&chaine, 15, 1, 2, 3, 31) == HAL_ERROR, "indice 15 refusé (hors chaîne)");
    VERIFIE(RgbLedChain_SetColor(&chaine, 0, 1, 2, 3, 32) == HAL_ERROR, "luminosité 32 refusée");
    VERIFIE(memcmp(avant, chaine.frame, sizeof avant) == 0, "image inchangée après refus");

    /* Show par DMA */
    VERIFIE(RgbLedChain_Show(&chaine) == HAL_OK, "Show DMA");
    VERIFIE(spi.dma_calls == 1 && spi.last_size == 68, "1 envoi DMA de 68 octets");
    VERIFIE(spi.last_data == chaine.tx_frame, "le DMA lit la copie tx_frame");
    VERIFIE(memcmp(chaine.tx_frame, chaine.frame, 68) == 0, "copie identique à l'image");

    /* Modifier l'image pendant le DMA ne touche pas à la trame en cours d'envoi */
    RgbLedChain_SetColor(&chaine, 0, 0, 255, 0, 31);
    VERIFIE(chaine.tx_frame[4] == 0xE0 && chaine.tx_frame[6] == 0x00, "tx_frame protégée pendant l'envoi");

    /* Show pendant que le DMA est occupé */
    VERIFIE(RgbLedChain_Show(&chaine) == HAL_BUSY, "Show refusé (HAL_BUSY) pendant le DMA");
    VERIFIE(spi.dma_calls == 1, "aucun 2e envoi lancé");

    /* Fin du DMA, puis nouvel envoi avec la nouvelle image */
    spi.State = HAL_SPI_STATE_READY;
    VERIFIE(RgbLedChain_Show(&chaine) == HAL_OK && spi.dma_calls == 2, "2e envoi après la fin du DMA");
    VERIFIE(chaine.tx_frame[6] == 0xFF, "2e envoi contient la DEL 0 en vert");

    /* Clear */
    spi.State = HAL_SPI_STATE_READY;
    VERIFIE(RgbLedChain_Clear(&chaine) == HAL_OK, "Clear");
    toutes_eteintes = 1;
    for (int i = 0; i < 15; i++) { if (memcmp(&chaine.frame[4 + 4 * i], eteinte, 4) != 0) toutes_eteintes = 0; }
    VERIFIE(toutes_eteintes && memcmp(&chaine.frame[64], uns, 4) == 0, "Clear éteint tout, fin de trame intacte");

    /* Repli sans DMA (ex. projet HAUT actuel) : envoi bloquant */
    SPI_HandleTypeDef spi_sans_dma = { .hdmatx = NULL, .State = HAL_SPI_STATE_READY };
    static RgbLedChain_HandleTypeDef barre;   /* PCB-08 de la borne : 8 DEL */
    VERIFIE(RgbLedChain_Init(&barre, &spi_sans_dma, 8) == HAL_OK && barre.frame_size == 40, "barre 8 DEL = 40 octets");
    VERIFIE(RgbLedChain_Show(&barre) == HAL_OK && spi_sans_dma.blocking_calls == 1, "envoi bloquant sans DMA");

    printf("%d/%d vérifications réussies\n", total - echecs, total);
    return echecs == 0 ? 0 : 1;
}
