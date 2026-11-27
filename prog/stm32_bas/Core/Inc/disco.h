/*
 * disco.h
 *
 *  Created on: 26 nov. 2026
 *      Author: William MacDonald (T07, animation d'essai)
 *
 * Animation « disco » sur les DEL d'un nœud. Elle passe par la surcouche de T07
 * (T07_DefinirSurcouche) : T07 compose son image normale (éclairage, ambiance,
 * témoins), puis la disco remplace la couleur des DEL de sa zone. Les autres DEL
 * gardent leur état normal, et T07 continue de recevoir les commandes et d'y
 * répondre. À l'arrêt, l'image normale revient d'elle-même.
 *
 * Zones :
 *   tout     : les 15 DEL de la PCB-03
 *   parkings : les 7 témoins du dessus seulement (sur le HAUT, l'ambiance des parkings)
 *   dessous  : les 8 DEL d'éclairage sous la carte seulement
 *
 * Modes :
 *   1 arc-en-ciel : les couleurs tournent autour de la carte (un tour en 3 s)
 *   2 stroboscope : flash d'une couleur au hasard à chaque temps (120 BPM), blanc tous les 4 temps
 *   3 poursuite   : une comète fait le tour de la carte, sa couleur change à chaque tour
 *
 * Hors protocole v1.6 : déclenchée par la console ou par les trames d'ESSAI
 * ci-dessous (voir essai_t07.c). Pour que le vrai RPi les commande, il faudrait
 * les ajouter au protocole (décision de l'équipe et de l'enseignant).
 */

#ifndef INC_DISCO_H_
#define INC_DISCO_H_

#include <stdbool.h>
#include <stdint.h>

#define DISCO_ARRET            0u
#define DISCO_ARC_EN_CIEL      1u
#define DISCO_STROBOSCOPE      2u
#define DISCO_POURSUITE        3u
#define DISCO_NB_MODES         3u

#define DISCO_ZONE_TOUT        0u
#define DISCO_ZONE_PARKINGS    1u
#define DISCO_ZONE_DESSOUS     2u

#define DISCO_INTENSITE_DEFAUT 60u   /* % : limite le courant (environ 0,85 A par PCB-03 en blanc à 100 %) */
#define DISCO_PERIODE_IMAGE_MS 25u   /* 40 images par seconde */

/* Trames d'ESSAI, hors protocole v1.6 :
 *   0x7F0 disco    [mode 0-3, cible, intensité %, zone (facultatif, 0 par défaut)]
 *   0x7F1 ambiance [R, V, B] : éclairage des parkings du HAUT (témoins du dessus)
 * cible : 1 = BAS, 2 = HAUT, 3 = BORNE (PCB-03 du milieu), 0xFF = tous. */
#define CAN_ID_ESSAI_DISCO     0x7F0u
#define CAN_ID_ESSAI_AMBIANCE  0x7F1u
#define DISCO_CIBLE_TOUS       0xFFu

/* mode 0 = arrêt ; zone : DISCO_ZONE_* ; intensite en % (0 à 100). false si mode ou zone invalide. */
bool    Disco_Choisir(uint8_t mode, uint8_t zone, uint8_t intensite, uint32_t maintenant_ms);
uint8_t Disco_Mode(void);
uint8_t Disco_Zone(void);

#endif /* INC_DISCO_H_ */
