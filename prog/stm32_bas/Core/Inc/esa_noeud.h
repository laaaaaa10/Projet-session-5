/*
 * esa_noeud.h
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald
 *
 * Choix du nœud ESA compilé dans ce projet. Les modules partagés entre les
 * trois STM32 (T07, heartbeat) lisent ESA_NOEUD pour choisir leurs
 * identifiants CAN et leur configuration.
 */

#ifndef INC_ESA_NOEUD_H_
#define INC_ESA_NOEUD_H_

#define ESA_NOEUD_BAS     1
#define ESA_NOEUD_HAUT    2
#define ESA_NOEUD_BORNE   3

/* Ce projet : STM32 BAS */
#ifndef ESA_NOEUD
#define ESA_NOEUD   ESA_NOEUD_BAS
#endif

#endif /* INC_ESA_NOEUD_H_ */
