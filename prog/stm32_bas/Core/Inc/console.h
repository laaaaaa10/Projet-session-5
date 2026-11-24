/*
 * console.h
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald
 *
 * Console de débogage non bloquante, en même temps sur :
 *   - l'USB de la Discovery (port COM virtuel CDC, connecteur micro-USB) ;
 *   - l'USART2 (PA2/PA3), qui arrive au pont USB-série CH340X du PCB-12.
 *
 * Sortie : Console_Ecrire() et Console_Printf() copient le texte dans une file
 * d'attente et reviennent tout de suite ; Console_Tache() envoie la file dès
 * que l'USB ou l'UART est libre. Sans terminal ouvert, le texte est conservé
 * jusqu'à remplir la file, puis les plus vieux messages sont abandonnés.
 *
 * Entrée : les caractères reçus (USB ou UART) sont mis en file en interruption ;
 * Console_LireLigne() les assemble en lignes dans la boucle principale, avec
 * écho et retour arrière.
 */

#ifndef INC_CONSOLE_H_
#define INC_CONSOLE_H_

#include <stdbool.h>
#include <stdint.h>

/* Démarre la réception sur l'USART2. */
void Console_Init(void);

/* Ajoute un texte à envoyer. */
void Console_Ecrire(const char *texte);

/* Comme printf (128 caractères au maximum par appel). */
void Console_Printf(const char *format, ...);

/* À appeler à chaque tour de la boucle principale. */
void Console_Tache(void);

/* Octets reçus (appelée par CDC_Receive_FS, en interruption). */
void Console_RecevoirOctets(const uint8_t *data, uint32_t longueur);

/* true quand une ligne complète a été tapée (copiée sans le retour de chariot). */
bool Console_LireLigne(char *ligne, uint16_t taille);

#endif /* INC_CONSOLE_H_ */
