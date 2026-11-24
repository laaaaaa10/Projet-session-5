/*
 * essai_del.h
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald (T07)
 *
 * Essai de banc de la chaîne de DEL du PCB-03 (préparation de TU-09), sans CAN.
 * Allume une seule DEL à la fois, en rouge, vert, bleu puis blanc, et affiche
 * son indice sur la console (USB de la Discovery ou USART2, voir console.h).
 * Le bouton bleu met en pause sur la DEL courante. La DEL verte de la
 * Discovery clignote (indicateur de vie).
 *
 * Sert aussi à relever la position physique de chaque indice (témoin sur le
 * dessus ou éclairage sous la carte, et ouverture correspondante).
 *
 * Module temporaire : il sera remplacé par le module T07 (commandes CAN).
 */

#ifndef INC_ESSAI_DEL_H_
#define INC_ESSAI_DEL_H_

/* Prépare la chaîne et éteint toutes les DEL. */
void EssaiDel_Init(void);

/* À appeler à chaque tour de la boucle principale (non bloquant). */
void EssaiDel_Tache(void);

#endif /* INC_ESSAI_DEL_H_ */
