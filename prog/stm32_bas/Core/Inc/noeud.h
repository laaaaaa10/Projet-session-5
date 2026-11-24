/*
 * noeud.h
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald
 *
 * Services communs du nœud (Protocole CAN v1.6, section 4) :
 *   - émet son heartbeat toutes les 500 ms (0x042 pour le BAS) ;
 *   - surveille le heartbeat du RPi (0x040) : perte après 1,5 s sans trame ;
 *   - lit les trames CAN reçues et les aiguille vers les modules (T07, puis T06).
 *
 * La DEL verte de la Discovery bascule à chaque heartbeat émis (indicateur de vie)
 * et la DEL bleue est allumée tant que le RPi est en ligne.
 */

#ifndef INC_NOEUD_H_
#define INC_NOEUD_H_

#include <stdbool.h>
#include <stdint.h>
#include "esa_can.h"

#define NOEUD_PERIODE_HEARTBEAT_MS   500u
#define NOEUD_DELAI_PERTE_RPI_MS     1500u   /* 3 périodes manquées (seuil à valider sur banc) */

/* Fonction appelée pour chaque trame reçue (trace d'essai) ; NULL pour aucune. */
typedef void (*Noeud_Observateur)(const TrameCan *trame);

void Noeud_Init(uint32_t maintenant_ms);
void Noeud_Tache(uint32_t maintenant_ms);
void Noeud_DefinirObservateur(Noeud_Observateur observateur);
bool Noeud_RpiEnLigne(void);

#endif /* INC_NOEUD_H_ */
