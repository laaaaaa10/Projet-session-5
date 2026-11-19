/*
 * temp_test.h
 *
 * *** FICHIER TEMPORAIRE : a supprimer quand tout fonctionne ***
 * Voir la liste de ce qu'il faut enlever en haut de temp_test.c.
 */

#ifndef TEMP_TEST_H_
#define TEMP_TEST_H_

#include "stm32f4xx_hal.h"
#include "inductive_sensor.h"

/* A appeler dans la boucle. Lit les 3 capteurs et affiche une ligne avec l'etat des 3 etages
 * (a chaque passage, au plus toutes les 500 ms, et tout de suite si un capteur change). */
void TempTest_Floor(InductiveSensor_HandleTypeDef *dev);

#endif /* TEMP_TEST_H_ */
