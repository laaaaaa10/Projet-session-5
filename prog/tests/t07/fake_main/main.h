/* Faux main.h pour tester noeud.c sur PC. */
#ifndef FAKE_MAIN_H
#define FAKE_MAIN_H
#include "stm32f4xx_hal.h"
typedef struct { int dummy; } GPIO_TypeDef;
typedef enum { GPIO_PIN_RESET = 0, GPIO_PIN_SET } GPIO_PinState;
extern GPIO_TypeDef GPIOD_fake;
#define LED_VERTE_GPIO_Port (&GPIOD_fake)
#define LED_VERTE_Pin 12
#define LED_BLEUE_GPIO_Port (&GPIOD_fake)
#define LED_BLEUE_Pin 15
void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState etat);
void HAL_GPIO_TogglePin(GPIO_TypeDef *port, uint16_t pin);
#endif
