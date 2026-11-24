/*
 * essai_t07.h
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald (T07)
 *
 * Essai du module T07 depuis la console, sans RPi.
 * En loopback, le STM32 reçoit ses propres trames : une commande tapée dans
 * PuTTY passe donc réellement par le contrôleur CAN, puis par T07, qui
 * répond sur le CAN ; la réponse est affichée.
 *
 * Commandes (taper « aide ») :
 *   del <place> <R> <V> <B> [mode]   DEL_PLACE_CMD 0x340
 *   ecl <niveau> <R> <V> <B>         ECLAIRAGE_CMD 0x130
 *   brut <id hex> [octets hex...]    trame quelconque (cas invalides)
 *   hb on | off                      simule le heartbeat du RPi (0x040)
 *   etat | image | trace on|off | aide
 */

#ifndef INC_ESSAI_T07_H_
#define INC_ESSAI_T07_H_

#include <stdint.h>

void EssaiT07_Init(void);
void EssaiT07_Tache(uint32_t maintenant_ms);

#endif /* INC_ESSAI_T07_H_ */
