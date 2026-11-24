/*
 * Tests sur PC de noeud.c : heartbeat du BAS, surveillance du RPi, aiguillage vers T07.
 * Le service CAN est remplacé par une fausse file ; T07 est le vrai module.
 */
#include <stdio.h>
#include <string.h>
#include "main.h"
#include "noeud.h"
#include "t07_del.h"

/* ---- Faux GPIO ---- */
GPIO_TypeDef GPIOD_fake;
static int del_bleue = 0, bascules_verte = 0;
void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState etat) { (void)port; if (pin == LED_BLEUE_Pin) del_bleue = (etat == GPIO_PIN_SET); }
void HAL_GPIO_TogglePin(GPIO_TypeDef *port, uint16_t pin) { (void)port; if (pin == LED_VERTE_Pin) bascules_verte++; }

/* ---- Faux SPI (pour T07) ---- */
HAL_SPI_StateTypeDef HAL_SPI_GetState(SPI_HandleTypeDef *h) { return h->State; }
HAL_StatusTypeDef HAL_SPI_Transmit_DMA(SPI_HandleTypeDef *h, uint8_t *d, uint16_t n) { h->last_data = d; h->last_size = n; return HAL_OK; }
HAL_StatusTypeDef HAL_SPI_Transmit(SPI_HandleTypeDef *h, uint8_t *d, uint16_t n, uint32_t t) { (void)t; h->last_data = d; h->last_size = n; return HAL_OK; }

/* ---- Faux service CAN ---- */
static TrameCan file_rx[16]; static int rx_tete = 0, rx_queue = 0;
static TrameCan envoyees[256]; static int nb_envoyees = 0;
bool CanEsa_Recevoir(TrameCan *t) { if (rx_queue == rx_tete) return false; *t = file_rx[rx_queue++ % 16]; return true; }
bool CanEsa_Envoyer(uint16_t id, const uint8_t *d, uint8_t dlc) { TrameCan *t = &envoyees[nb_envoyees++ % 256]; t->id = id; t->dlc = dlc; memcpy(t->data, d, dlc); return true; }
static void recevoir(uint16_t id, uint8_t dlc, const uint8_t *d) { TrameCan *t = &file_rx[rx_tete++ % 16]; t->id = id; t->dlc = dlc; memset(t->data, 0, 8); memcpy(t->data, d, dlc); }

static int echecs = 0, total = 0;
#define VERIFIE(cond, msg) do { total++; if (!(cond)) { echecs++; printf("ECHEC : %s (ligne %d)\n", msg, __LINE__); } } while (0)

static int nb_observees = 0;
static void observateur(const TrameCan *t) { (void)t; nb_observees++; }

static int compte_id(uint16_t id) { int n = 0; for (int i = 0; i < nb_envoyees; i++) if (envoyees[i].id == id) n++; return n; }

int main(void)
{
    static DMA_HandleTypeDef dma; static SPI_HandleTypeDef spi = { .hdmatx = &dma, .State = HAL_SPI_STATE_READY };
    VERIFIE(T07_Init(&T07_CONFIG_BAS, &spi, CanEsa_Envoyer), "init T07");
    Noeud_Init(0);
    Noeud_DefinirObservateur(observateur);

    /* Heartbeat toutes les 500 ms */
    for (uint32_t t = 0; t <= 5000; t += 10) Noeud_Tache(t);
    VERIFIE(compte_id(0x042) == 10, "10 heartbeats 0x042 en 5 s");
    VERIFIE(envoyees[0].dlc == 2 && envoyees[0].data[0] == 0 && envoyees[0].data[1] == 1, "1er heartbeat [0, 1 prêt]");
    VERIFIE(envoyees[9].data[0] == 9, "compteur cyclique incrémenté");
    VERIFIE(bascules_verte == 10, "DEL verte basculée à chaque heartbeat");
    VERIFIE(!Noeud_RpiEnLigne() && !del_bleue, "RPi hors ligne au départ");

    /* Le RPi apparaît */
    uint8_t hb[2] = { 0, 1 };
    recevoir(0x040, 2, hb);
    Noeud_Tache(5010);
    VERIFIE(Noeud_RpiEnLigne() && T07_RpiEnLigne() && del_bleue, "heartbeat RPi reçu : en ligne (T07 informé, DEL bleue)");
    VERIFIE(nb_observees == 1, "trame transmise à l'observateur");

    /* Heartbeats réguliers jusqu'à 7000, puis plus rien */
    for (uint32_t t = 5020; t <= 7000; t += 10) { if (t % 500 == 0) recevoir(0x040, 2, hb); Noeud_Tache(t); }
    VERIFIE(Noeud_RpiEnLigne(), "toujours en ligne avec des heartbeats réguliers");
    for (uint32_t t = 7010; t < 8500; t += 10) Noeud_Tache(t);
    VERIFIE(Noeud_RpiEnLigne(), "1490 ms sans heartbeat : encore en ligne");
    Noeud_Tache(8500);
    VERIFIE(!Noeud_RpiEnLigne() && !T07_RpiEnLigne() && !del_bleue, "1500 ms sans heartbeat : perte détectée");

    /* Aiguillage d'une commande T07 */
    int avant = compte_id(0x341);
    uint8_t cmd[6] = { 5, 3, 255, 0, 0, 0 };
    recevoir(0x340, 6, cmd);
    Noeud_Tache(8510);
    VERIFIE(compte_id(0x341) == avant + 1, "commande 0x340 aiguillée vers T07, réponse 0x341");

    /* Retard de la boucle : pas de rafale de heartbeats */
    int hb_avant = compte_id(0x042);
    Noeud_Tache(12000);
    Noeud_Tache(12010);
    VERIFIE(compte_id(0x042) == hb_avant + 1, "après un long retard : un seul heartbeat, puis recalage");

    printf("%d/%d vérifications réussies\n", total - echecs, total);
    return echecs == 0 ? 0 : 1;
}
