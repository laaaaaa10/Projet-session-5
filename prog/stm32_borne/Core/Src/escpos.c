 /**
  * escpos.c - T05 : construcción de comandos ESC/POS en un búfer
  */
 #include "escpos.h"
 #include <string.h>

 #define ESC 0x1Bu
 #define LF  0x0Au
 #define GS  0x1Du
#define CODE128_PREFIXE_JEU_B    0

 /* Agrega n bytes al búfer, o marca desbordamiento sin escribir nada parcial */
 static void ajouter_octets(EscPosTampon *t, const uint8_t *src, uint16_t n)
 {
    if (t->debordement || (uint32_t)t->taille + n > t->capacite)
    {
        t->debordement = true;
        return;
    }
    memcpy(&t->donnees[t->taille], src, n);
    t->taille = (uint16_t)(t->taille + n);
 }

 void EscPos_Init(EscPosTampon *t, uint8_t *donnees, uint16_t capacite)
 {
    t->donnees     = donnees;
    t->capacite    = capacite;
    t->taille      = 0u;
    t->debordement = false;
 }

 void EscPos_Reinitialiser(EscPosTampon *t)
 {
    const uint8_t cmd[2] = { ESC, '@' };
    ajouter_octets(t, cmd, 2u);
 }

 void EscPos_Alignement(EscPosTampon *t, uint8_t align)
 {
    const uint8_t cmd[3] = { ESC, 'a', align };   /* 0 izq, 1 centro, 2 der */
    ajouter_octets(t, cmd, 3u);
 }

 void EscPos_Gras(EscPosTampon *t, bool actif)
 {
    const uint8_t cmd[3] = { ESC, 'E', actif ? 1u : 0u };
    ajouter_octets(t, cmd, 3u);
 }

 void EscPos_Ligne(EscPosTampon *t, const char *texte)
 {
    const uint8_t lf = LF;
    ajouter_octets(t, (const uint8_t *)texte, (uint16_t)strlen(texte));
    ajouter_octets(t, &lf, 1u);
 }
 void EscPos_TailleDouble(EscPosTampon *t, bool actif)
 {
     /* bits 0-3 : alto x2 ; bits 4-7 : ancho x2  →  0x11 = doble en ambos */
    const uint8_t cmd[3] = { GS, '!', actif ? 0x11u : 0x00u };
    ajouter_octets(t, cmd, 3u);
 }

 void EscPos_Avancer(EscPosTampon *t, uint8_t lignes)
 {
    const uint8_t cmd[3] = { ESC, 'd', lignes };
    ajouter_octets(t, cmd, 3u);
 }

 void EscPos_Code128(EscPosTampon *t, const char *donnees,
                    uint8_t hauteur, uint8_t largeur)
 {
    uint16_t n = (uint16_t)strlen(donnees);
    if (n == 0u || n > 60u)
    {
        t->debordement = true;   /* datos inválidos: se trata como error */
        return;
    }

    const uint8_t alto[3]  = { GS, 'h', hauteur };  /* alto de las barras (puntos) */
    const uint8_t ancho[3] = { GS, 'w', largeur };  /* ancho de una barra (2 a 6)  */
    const uint8_t hri[3]   = { GS, 'H', 2u };       /* número legible DEBAJO       */
    ajouter_octets(t, alto, 3u);
    ajouter_octets(t, ancho, 3u);
    ajouter_octets(t, hri, 3u);

#if CODE128_PREFIXE_JEU_B
    /* GS k 73 n  '{' 'B'  données... */
    const uint8_t entete[6] = { GS, 'k', 73u, (uint8_t)(n + 2u), '{', 'B' };
    ajouter_octets(t, entete, 6u);
#else
    /* GS k 73 n  données... (l'imprimante choisit le jeu automatiquement) */
    const uint8_t entete[4] = { GS, 'k', 73u, (uint8_t)n };
    ajouter_octets(t, entete, 4u);
#endif
    ajouter_octets(t, (const uint8_t *)donnees, n);

    const uint8_t lf = LF;
    ajouter_octets(t, &lf, 1u);
}
 void EscPos_Image(EscPosTampon *t, const uint8_t *bitmap,
                   uint16_t largeur_octets, uint16_t hauteur)
 {
     uint32_t taille = (uint32_t)largeur_octets * hauteur;
     if (taille == 0u || taille > 0xFFFFu)
     {
         t->debordement = true;
         return;
     }

     /* GS v 0 m xL xH yL yH : m = 0 (taille normale), x en octets, y en points */
     const uint8_t entete[8] = { GS, 'v', '0', 0u,
                                 (uint8_t)(largeur_octets & 0xFFu), (uint8_t)(largeur_octets >> 8),
                                 (uint8_t)(hauteur & 0xFFu),        (uint8_t)(hauteur >> 8) };
     ajouter_octets(t, entete, 8u);
     ajouter_octets(t, bitmap, (uint16_t)taille);
 }
