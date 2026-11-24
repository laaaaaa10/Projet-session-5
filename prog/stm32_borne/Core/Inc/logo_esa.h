/**
 * @file    logo_esa.h
 * @brief   T05 - Logo du billet (bitmap 1 bit, généré par image_vers_c.py).
 *
 * Projet ESA - 243-557 - Automne 2026
 */
#ifndef LOGO_ESA_H
#define LOGO_ESA_H

#include <stdint.h>

#define LOGO_ESA_LARGEUR_OCTETS  24u   /* 192 points */
#define LOGO_ESA_HAUTEUR         64u   /* lignes de points */

extern const uint8_t LOGO_ESA[LOGO_ESA_LARGEUR_OCTETS * LOGO_ESA_HAUTEUR];

#endif /* LOGO_ESA_H */
