 /**
  * escpos.h - T05 : construcción de comandos ESC/POS en un búfer
  */
 #ifndef ESCPOS_H
 #define ESCPOS_H

 #include <stdbool.h>
 #include <stdint.h>

 typedef struct
 {
    uint8_t *donnees;     /* el arreglo donde escribimos          */
    uint16_t capacite;    /* tamaño máximo del arreglo            */
    uint16_t taille;      /* cuántos bytes llevamos escritos      */
    bool     debordement; /* true si algo no cupo                 */
 } EscPosTampon;

 void EscPos_Init(EscPosTampon *t, uint8_t *donnees, uint16_t capacite);
 void EscPos_Reinitialiser(EscPosTampon *t);                /* ESC @   */
 void EscPos_Alignement(EscPosTampon *t, uint8_t align);    /* ESC a n */
 void EscPos_Gras(EscPosTampon *t, bool actif);             /* ESC E n */
 void EscPos_Ligne(EscPosTampon *t, const char *texte);     /* texto + LF */
 void EscPos_TailleDouble(EscPosTampon *t, bool actif);     /* GS ! n  */
 void EscPos_Avancer(EscPosTampon *t, uint8_t lignes);      /* ESC d n */
 void EscPos_Code128(EscPosTampon *t, const char *donnees,
                    uint8_t hauteur, uint8_t largeur);     /* GS k    */

 void EscPos_Image(EscPosTampon *t, const uint8_t *bitmap,
                   uint16_t largeur_octets, uint16_t hauteur);
 #endif /* ESCPOS_H */
 
