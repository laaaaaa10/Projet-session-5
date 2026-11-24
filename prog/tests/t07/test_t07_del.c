/*
 * Tests sur PC du module T07 (logique des commandes CAN et image des DEL).
 * Utilise le vrai pilote rgb_led_chain.c avec un faux HAL (fake_hal/).
 */
#include <stdio.h>
#include <string.h>
#include "t07_del.h"

/* ---- Faux HAL SPI ---- */
static int spi_occupe_force = 0;
HAL_SPI_StateTypeDef HAL_SPI_GetState(SPI_HandleTypeDef *hspi)
{
    return spi_occupe_force ? HAL_SPI_STATE_BUSY_TX : hspi->State;
}
HAL_StatusTypeDef HAL_SPI_Transmit_DMA(SPI_HandleTypeDef *hspi, uint8_t *pData, uint16_t Size)
{
    hspi->last_data = pData; hspi->last_size = Size; hspi->dma_calls++;
    return HAL_OK;                                  /* DMA « instantané » */
}
HAL_StatusTypeDef HAL_SPI_Transmit(SPI_HandleTypeDef *hspi, uint8_t *pData, uint16_t Size, uint32_t Timeout)
{
    (void)Timeout; hspi->last_data = pData; hspi->last_size = Size; hspi->blocking_calls++;
    return HAL_OK;
}

/* ---- Espion CAN ---- */
typedef struct { uint16_t id; uint8_t dlc; uint8_t data[8]; } Trame;
static Trame envoyees[64];
static int nb_envoyees = 0;
static bool espion_envoyer(uint16_t id, const uint8_t *data, uint8_t dlc)
{
    if (nb_envoyees < 64) { envoyees[nb_envoyees].id = id; envoyees[nb_envoyees].dlc = dlc; memcpy(envoyees[nb_envoyees].data, data, dlc); }
    nb_envoyees++;
    return true;
}

/* ---- Mini cadre de test ---- */
static int echecs = 0, total = 0;
#define VERIFIE(cond, msg) do { total++; if (!(cond)) { echecs++; printf("ECHEC : %s (ligne %d)\n", msg, __LINE__); } } while (0)

static DMA_HandleTypeDef dma;
static SPI_HandleTypeDef spi = { .hdmatx = &dma, .State = HAL_SPI_STATE_READY };

/* Lit la couleur d'une DEL dans la dernière trame envoyée sur le SPI. */
static void del_envoyee(uint8_t indice, uint8_t *r, uint8_t *v, uint8_t *b, uint8_t *lum)
{
    const uint8_t *p = &spi.last_data[4 + 4 * indice];
    *lum = p[0] & 0x1F; *b = p[1]; *v = p[2]; *r = p[3];
}
static int del_est(uint8_t indice, uint8_t r, uint8_t v, uint8_t b)
{
    uint8_t rr, vv, bb, ll; del_envoyee(indice, &rr, &vv, &bb, &ll);
    return rr == r && vv == v && bb == b && ll == T07_LUMINOSITE_GLOBALE;
}
static void cmd(uint16_t id, uint8_t dlc, uint8_t d0, uint8_t d1, uint8_t d2, uint8_t d3, uint8_t d4, uint8_t d5)
{
    uint8_t d[8] = { d0, d1, d2, d3, d4, d5, 0, 0 };
    T07_TraiterTrame(id, dlc, d);
}
static int derniere_reponse(uint16_t id, uint8_t seq, uint8_t val, uint8_t res)
{
    if (nb_envoyees == 0) return 0;
    Trame *t = &envoyees[nb_envoyees - 1];
    return t->id == id && t->dlc == 3 && t->data[0] == seq && t->data[1] == val && t->data[2] == res;
}

int main(void)
{
    uint32_t t = 0;

    /* ===== Nœud BAS ===== */
    VERIFIE(T07_Init(&T07_CONFIG_BAS, &spi, espion_envoyer), "init BAS");
    VERIFIE(spi.dma_calls == 0, "rien n'est envoyé avant T07_Tache");
    T07_Tache(t);
    VERIFIE(spi.dma_calls == 1 && spi.last_size == 68, "1er envoi : trame de 15 DEL");
    int ok = 1;
    for (int k = 1; k <= 13; k += 2) ok &= del_est(k, 0, 0, 0);
    VERIFIE(ok, "démarrage : 7 témoins éteints (indices impairs)");
    ok = 1;
    for (int k = 0; k <= 14; k += 2) ok &= del_est(k, 64, 64, 64);
    VERIFIE(ok, "démarrage : éclairage blanc modéré (indices pairs)");

    T07_Tache(t + 10);
    VERIFIE(spi.dma_calls == 1, "aucun envoi si l'image ne change pas");

    /* Commande valide : place 3 rouge fixe */
    cmd(0x340, 6, 7, 3, 255, 0, 0, 0);
    VERIFIE(derniere_reponse(0x341, 7, 3, 1), "place 3 : réponse 0x341 [7, 3, 1]");
    T07_Tache(t + 20);
    VERIFIE(spi.dma_calls == 2 && del_est(5, 255, 0, 0), "place 3 = indice 5 en rouge");
    VERIFIE(del_est(3, 0, 0, 0) && del_est(7, 0, 0, 0), "places voisines inchangées");

    /* Places 1 et 7 (bornes de la plage) */
    cmd(0x340, 6, 8, 1, 0, 255, 0, 0);
    cmd(0x340, 6, 9, 7, 0, 0, 255, 0);
    T07_Tache(t + 30);
    VERIFIE(del_est(1, 0, 255, 0) && del_est(13, 0, 0, 255), "place 1 = indice 1 (vert), place 7 = indice 13 (bleu)");

    /* Place du HAUT : ignorée, sans réponse */
    int avant = nb_envoyees;
    cmd(0x340, 6, 10, 8, 1, 2, 3, 0);
    cmd(0x340, 6, 11, 14, 1, 2, 3, 0);
    VERIFIE(nb_envoyees == avant, "places 8 et 14 (HAUT) : aucune réponse du BAS");

    /* Refus */
    cmd(0x340, 6, 12, 0, 1, 2, 3, 0);
    VERIFIE(derniere_reponse(0x341, 12, 0, 0), "place 0 refusée");
    cmd(0x340, 6, 13, 15, 1, 2, 3, 0);
    VERIFIE(derniere_reponse(0x341, 13, 15, 0), "place 15 refusée");
    cmd(0x340, 5, 14, 3, 0, 255, 0, 0);
    VERIFIE(derniere_reponse(0x341, 14, 3, 0), "DLC 5 refusé");
    cmd(0x340, 1, 15, 0, 0, 0, 0, 0);
    VERIFIE(derniere_reponse(0x341, 15, 0, 0), "DLC 1 (place absente) refusé");
    cmd(0x340, 6, 16, 3, 0, 255, 0, 2);
    VERIFIE(derniere_reponse(0x341, 16, 3, 0), "mode 2 refusé");
    T07_Tache(t + 40);
    VERIFIE(del_est(5, 255, 0, 0), "après les refus, place 3 toujours rouge");

    /* Clignotement 1 Hz : place 2 jaune clignotant */
    cmd(0x340, 6, 17, 2, 255, 255, 0, 1);
    VERIFIE(derniere_reponse(0x341, 17, 2, 1), "place 2 clignotante appliquée");
    T07_Tache(1000);  VERIFIE(del_est(3, 255, 255, 0), "t = 1000 ms : allumée");
    T07_Tache(1499);  VERIFIE(del_est(3, 255, 255, 0), "t = 1499 ms : allumée");
    T07_Tache(1500);  VERIFIE(del_est(3, 0, 0, 0),     "t = 1500 ms : éteinte");
    VERIFIE(del_est(5, 255, 0, 0), "la place fixe ne clignote pas");
    T07_Tache(1999);  VERIFIE(del_est(3, 0, 0, 0),     "t = 1999 ms : éteinte");
    T07_Tache(2000);  VERIFIE(del_est(3, 255, 255, 0), "t = 2000 ms : rallumée (période 1 s)");

    /* Éclairage */
    cmd(0x130, 5, 20, 0, 10, 20, 30, 0);
    VERIFIE(derniere_reponse(0x350, 20, 0, 1), "éclairage niveau 0 : réponse 0x350 [20, 0, 1]");
    T07_Tache(2010);
    ok = 1;
    for (int k = 0; k <= 14; k += 2) ok &= del_est(k, 10, 20, 30);
    VERIFIE(ok, "éclairage appliqué aux 8 DEL d'indice pair");
    avant = nb_envoyees;
    cmd(0x130, 5, 21, 1, 1, 1, 1, 0);
    cmd(0x130, 5, 22, 2, 1, 1, 1, 0);
    VERIFIE(nb_envoyees == avant, "niveaux 1 et 2 : ignorés par le BAS");
    cmd(0x130, 5, 23, 3, 1, 1, 1, 0);
    VERIFIE(derniere_reponse(0x350, 23, 3, 0), "niveau 3 refusé");
    cmd(0x130, 4, 24, 0, 1, 1, 1, 0);
    VERIFIE(derniere_reponse(0x350, 24, 0, 0), "éclairage DLC 4 refusé");
    cmd(0x130, 0, 0, 0, 0, 0, 0, 0);
    VERIFIE(derniere_reponse(0x350, 0, 0xFF, 0), "éclairage DLC 0 refusé (niveau inconnu)");
    T07_Tache(2020);
    VERIFIE(del_est(0, 10, 20, 30), "éclairage inchangé après les refus");

    /* Autres identifiants : ignorés */
    avant = nb_envoyees;
    cmd(0x341, 3, 1, 1, 1, 0, 0, 0);
    cmd(0x100, 3, 1, 1, 1, 0, 0, 0);
    VERIFIE(nb_envoyees == avant, "trames non T07 ignorées");

    /* Perte puis retour du RPi */
    T07_SignalerRpi(true);
    T07_SignalerRpi(false);
    VERIFIE(!T07_RpiEnLigne(), "RPi hors ligne");
    T07_Tache(3000);
    ok = 1;
    for (int k = 1; k <= 13; k += 2) ok &= del_est(k, 255, 255, 0);
    VERIFIE(ok, "perte du RPi : 7 témoins jaunes (phase allumée)");
    VERIFIE(del_est(0, 10, 20, 30), "perte du RPi : éclairage conservé");
    T07_Tache(3500);
    VERIFIE(del_est(5, 0, 0, 0), "perte du RPi : témoins éteints (phase éteinte)");
    T07_SignalerRpi(true);
    T07_Tache(4000);
    VERIFIE(del_est(5, 255, 255, 0), "RPi revenu sans consigne : toujours jaune clignotant");
    cmd(0x340, 6, 30, 3, 255, 0, 0, 0);
    T07_Tache(4500);
    VERIFIE(del_est(5, 255, 0, 0), "consigne renvoyée : place 3 de nouveau rouge");
    VERIFIE(del_est(1, 0, 0, 0), "place 1 sans consigne : jaune, phase éteinte à 4500 ms");
    T07_Place p;
    VERIFIE(T07_LirePlace(3, &p) && p.etat == T07_PLACE_VALIDE, "place 3 valide");
    VERIFIE(T07_LirePlace(1, &p) && p.etat == T07_PLACE_INCONNUE, "place 1 inconnue");
    VERIFIE(!T07_LirePlace(8, &p), "place 8 n'appartient pas au BAS");

    /* SPI occupé : l'envoi est repris au prochain appel */
    int envois = spi.dma_calls;
    cmd(0x340, 6, 31, 4, 1, 2, 3, 0);
    spi_occupe_force = 1;
    T07_Tache(4600);
    VERIFIE(spi.dma_calls == envois, "SPI occupé : pas d'envoi");
    spi_occupe_force = 0;
    T07_Tache(4610);
    VERIFIE(spi.dma_calls == envois + 1 && del_est(7, 1, 2, 3), "envoi repris quand le SPI est libre");

    T07_Stats s = T07_LireStats();
    VERIFIE(s.reponses_non_envoyees == 0, "toutes les réponses ont été envoyées");

    /* ===== Nœud HAUT ===== */
    nb_envoyees = 0;
    VERIFIE(T07_Init(&T07_CONFIG_HAUT, &spi, espion_envoyer), "init HAUT");
    T07_Tache(0);
    cmd(0x340, 6, 40, 8, 0, 255, 0, 0);
    VERIFIE(derniere_reponse(0x342, 40, 8, 1), "HAUT : place 8 → réponse 0x342");
    avant = nb_envoyees;
    cmd(0x340, 6, 41, 7, 0, 255, 0, 0);
    VERIFIE(nb_envoyees == avant, "HAUT : place 7 (BAS) ignorée");
    cmd(0x130, 5, 42, 1, 5, 5, 5, 0);
    VERIFIE(derniere_reponse(0x351, 42, 1, 1), "HAUT : éclairage niveau 1 → 0x351");
    T07_Tache(10);
    VERIFIE(del_est(1, 0, 255, 0) && del_est(0, 5, 5, 5), "HAUT : place 8 = indice 1, éclairage indices pairs");

    /* ===== Borne ===== */
    nb_envoyees = 0;
    VERIFIE(T07_Init(&T07_CONFIG_BORNE, &spi, espion_envoyer), "init BORNE");
    T07_Tache(0);
    VERIFIE(spi.last_size == 40, "BORNE : trame de 8 DEL");
    cmd(0x340, 6, 50, 3, 1, 1, 1, 0);
    cmd(0x340, 6, 51, 0, 1, 1, 1, 0);
    VERIFIE(nb_envoyees == 0, "BORNE : aucune réponse aux commandes de places");
    cmd(0x130, 5, 52, 2, 200, 100, 50, 0);
    VERIFIE(derniere_reponse(0x352, 52, 2, 1), "BORNE : éclairage niveau 2 → 0x352");
    T07_Tache(10);
    ok = 1;
    for (int k = 0; k < 8; k++) ok &= del_est(k, 200, 100, 50);
    VERIFIE(ok, "BORNE : 8 DEL d'éclairage");
    T07_SignalerRpi(true); T07_SignalerRpi(false);
    T07_Tache(20);
    VERIFIE(del_est(0, 200, 100, 50), "BORNE : perte du RPi, éclairage conservé");

    printf("%d/%d vérifications réussies\n", total - echecs, total);
    return echecs == 0 ? 0 : 1;
}
