/*
 * temp_test.h
 *
 * *** FICHIER TEMPORAIRE : a supprimer quand tout fonctionne ***
 * Voir la liste de ce qu'il faut enlever en haut de temp_test.c.
 */

#ifndef TEMP_TEST_H_
#define TEMP_TEST_H_

#include <stdio.h>
#include "stm32f4xx_hal.h"
#include "inductive_sensor.h"

/* Scan I2C1 + resultat de ClickBoard_InitPWM, par printf. A appeler une fois apres l'init. */
void TempTest_ClickBoard(I2C_HandleTypeDef *hi2c, HAL_StatusTypeDef init_status);

/* Lit les 3 capteurs d'etage et affiche les changements (reaffiche l'etat toutes les 3 s). */
void TempTest_Floor(InductiveSensor_HandleTypeDef *dev);

#endif /* TEMP_TEST_H_ */
