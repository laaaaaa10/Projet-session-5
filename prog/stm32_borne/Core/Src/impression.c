/**
 * impression.c - T05 : composición del billete a partir de los datos recibidos
 */
#include "impression.h"
#include <stdio.h>

#define PLACES_PAR_ETAGE 7u

bool Impression_ComposerBillet(const DonneesBillet *d, EscPosTampon *t)
{
    char ligne[33];      /* 32 caracteres por línea + '\0' */
    char numero[12];

    /* Plaza 1..14  →  "E1.1" .. "E2.7" */
    uint8_t etage = (uint8_t)(1u + (d->place - 1u) / PLACES_PAR_ETAGE);
    uint8_t rang  = (uint8_t)(1u + (d->place - 1u) % PLACES_PAR_ETAGE);

    /* Número siempre con 6 cifras: 4213 → "004213" */
    snprintf(numero, sizeof(numero), "%06lu", (unsigned long)d->transaction);

    EscPos_Reinitialiser(t);

    /* Encabezado */
    EscPos_Alignement(t, 1);
    EscPos_TailleDouble(t, true);
    EscPos_Gras(t, true);
    EscPos_Ligne(t, "ESA");
    EscPos_TailleDouble(t, false);
    EscPos_Gras(t, false);
    EscPos_Ligne(t, "Cegep Limoilou");
    EscPos_Ligne(t, "--------------------------------");

    /* Detalles: se arman con snprintf a partir de las variables */
    EscPos_Alignement(t, 0);
    snprintf(ligne, sizeof(ligne), "Date  : 20%02u-%02u-%02u",
             d->annee, d->mois, d->jour);
    EscPos_Ligne(t, ligne);
    snprintf(ligne, sizeof(ligne), "Heure : %02u:%02u:%02u",
             d->heure, d->minute, d->seconde);
    EscPos_Ligne(t, ligne);
    snprintf(ligne, sizeof(ligne), "Place : E%u.%u", etage, rang);
    EscPos_Ligne(t, ligne);
    EscPos_Ligne(t, "--------------------------------");

    /* Número y código de barras */
    EscPos_Alignement(t, 1);
    EscPos_Ligne(t, "No de transaction");
    EscPos_Code128(t, numero, 80, 3);
    EscPos_Avancer(t, 4);

    return !t->debordement;
}