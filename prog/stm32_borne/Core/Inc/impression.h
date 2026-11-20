/**
 * impression.h - T05 : composicion del billete a partir de los datos recibidos
 */
#ifndef IMPRESSION_H
#define IMPRESSION_H

#include <stdbool.h>
#include <stdint.h>
#include "escpos.h"

/* Los datos que envia el RPi (tramas 0x360 y 0x361) */
typedef struct
{
    uint32_t transaction;  /* 0 a 999999 (T04)           */
    uint8_t  place;        /* 1 a 14                      */
    uint8_t  annee;        /* años desde 2000 (26 = 2026) */
    uint8_t  mois;
    uint8_t  jour;
    uint8_t  heure;
    uint8_t  minute;
    uint8_t  seconde;
} DonneesBillet;

/* Arma el billete completo en el búfer. Devuelve false si no cupo. */
bool Impression_ComposerBillet(const DonneesBillet *d, EscPosTampon *t);

#endif /* IMPRESSION_H */