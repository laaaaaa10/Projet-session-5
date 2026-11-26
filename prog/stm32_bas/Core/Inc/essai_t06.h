/*
 * essai_t06.h
 *
 *  Created on: 25 nov. 2026
 *      Author: William MacDonald (T06)
 *
 * Essai de T06 depuis la console (commandes ajoutées à celles d'essai_t07).
 *
 *   ir             état des 16 circuits, validité, compteurs
 *   ir brut        dernières lectures brutes : quels récepteurs voient la porteuse
 *                  pour chaque émetteur (sert à relever le câblage et le sens)
 *   ir lire        envoie IR_LECTURE_CMD 0x302 [1] ; la réponse 0x301 s'affiche
 *   demo on | off  faux RPi (CAN en loopback) : chaque 0x300 / 0x301 reçu déclenche
 *                  des 0x340 : place libre en vert, occupée en rouge ; demo off éteint
 *                  les témoins et l'éclairage (sinon T07 garde la dernière consigne)
 *   demo reserve | reparation | normal <place>
 *                  état logique d'une place : réservée = bleu (rouge si occupée),
 *                  réparation = jaune, normale = vert / rouge selon l'IR
 *   demo etat      état logique et occupation des 14 places
 * L'éclairage se commande avec ecl (essai_t07), même pendant la démo.
 *
 * Les trames 0x300 et 0x301 reçues sont décodées et affichées.
 */

#ifndef INC_ESSAI_T06_H_
#define INC_ESSAI_T06_H_

#include <stdbool.h>
#include <stdint.h>
#include "esa_can.h"

void EssaiT06_Aide(void);
bool EssaiT06_Executer(char **jetons, uint8_t n);   /* true si la commande est de T06 */
void EssaiT06_ObserverTrame(const TrameCan *t);
const char *EssaiT06_NomTrame(uint16_t id);          /* "" si inconnue */
void EssaiT06_Tache(uint32_t maintenant_ms);
void EssaiT06_RafraichirDemo(void);                  /* renvoie la couleur des 14 places si la démo est active */

#endif /* INC_ESSAI_T06_H_ */
