/**
 * @file    impression.c
 * @brief   T05 - Impression des billets (voir impression.h).
 *
 * Projet ESA - 243-557 - Automne 2026
 */
#include "impression.h"

#include <stdio.h>
#include <string.h>

#include "main.h"        /* HAL_GetTick, HAL_UART_Transmit_IT */
#include "can_borne.h"   /* CanBorne_Envoyer */
#include "logo_esa.h"    /* LOGO_ESA : bitmap du logo */

/* ========================================================================= */
/* Paramètres                                                                */
/* ========================================================================= */

#define PLACES_PAR_ETAGE         7u
#define NB_PLACES                14u
#define TRANSACTION_MAX          999999u
#define DELAI_APPARIEMENT_MS     1000u    /* protocole v1.6 : ~1 s              */
#define DELAI_DOUBLON_MS         10000u   /* fenêtre de détection des répétitions */
#define NB_HISTORIQUE            4u       /* demandes terminées mémorisées      */
#define TEXTE_TARIF              "Tarif : 0,10 $ / minute"
#define DELAI_UART_MS            5000u    /* envoi d'un billet avec logo : ~2 s à 9600 bauds */

/* UART de sortie du billet :
 *   huart3 = imprimante (PD8/PB11)
 *   huart2 = PuTTY, pour les essais sans imprimante
 * L'interruption globale de cet USART doit être activée dans CubeMX (NVIC). */
#define UART_BILLET              huart2
extern UART_HandleTypeDef UART_BILLET;

/* ========================================================================= */
/* États internes                                                            */
/* ========================================================================= */

/* Demande en cours d'appariement (une seule à la fois) */
typedef struct
{
    bool          active;      /* une demande attend-elle sa 2e trame ? */
    uint8_t       sequence;    /* DB0 commun aux deux trames             */
    bool          cmd_recue;   /* 0x360 reçue                            */
    bool          date_recue;  /* 0x361 reçue                            */
    DonneesBillet donnees;
    uint32_t      t_debut_ms;  /* arrivée de la première trame           */
} Demande;

/* Demande terminée, conservée pour reconnaître une répétition accidentelle */
typedef struct
{
    bool     valide;
    uint8_t  sequence;
    uint32_t transaction;
    uint8_t  resultat;     /* dernier résultat envoyé au RPi */
    uint8_t  erreur;
    uint32_t t_fin_ms;
} Historique;

/* Envoi UART en cours */
typedef struct
{
    bool          en_cours;
    uint8_t       sequence;
    uint32_t      transaction;
    uint32_t      t_debut_ms;
    volatile bool fin;       /* écrit par le callback HAL (interruption) */
    volatile bool succes;
} EnvoiUart;

static Demande    s_demande;
static Historique s_historique[NB_HISTORIQUE];
static uint8_t    s_prochain_historique;
static EnvoiUart  s_uart;
static uint8_t    s_memoire[2048];  /* tampon ESC/POS (logo ~1,5 ko) : doit rester valide pendant l'envoi */

/* ========================================================================= */
/* Fonctions internes                                                        */
/* ========================================================================= */

/* Temps écoulé ; la soustraction non signée reste correcte au débordement */
static uint32_t ecoule_ms(uint32_t depuis)
{
    return (uint32_t)(HAL_GetTick() - depuis);
}

/* Envoie IMPRESSION_ETAT (0x230) : DB0 séquence, DB1 résultat, DB2 erreur */
static void envoyer_etat(uint8_t sequence, uint8_t resultat, uint8_t erreur)
{
    const uint8_t trame[3] = { sequence, resultat, erreur };
    CanBorne_Envoyer(CAN_ID_IMPRESSION_ETAT, trame, 3);
}

static bool est_bissextile(uint16_t annee)
{
    return ((annee % 4u) == 0u && (annee % 100u) != 0u) || (annee % 400u) == 0u;
}

/* Vérifie qu'une date et une heure existent réellement (ex. refuse le 30 février) */
static bool date_valide(const DonneesBillet *d)
{
    static const uint8_t jours_par_mois[12] = { 31, 28, 31, 30, 31, 30,
                                                31, 31, 30, 31, 30, 31 };
    if (d->annee > 99u || d->mois < 1u || d->mois > 12u)
    {
        return false;
    }
    uint8_t jours_max = jours_par_mois[d->mois - 1u];
    if (d->mois == 2u && est_bissextile((uint16_t)(2000u + d->annee)))
    {
        jours_max = 29u;
    }
    return d->jour >= 1u && d->jour <= jours_max
        && d->heure <= 23u && d->minute <= 59u && d->seconde <= 59u;
}

/* --- Historique (détection des répétitions) ------------------------------ */

static Historique *chercher_historique(uint8_t sequence)
{
    for (uint8_t i = 0u; i < NB_HISTORIQUE; i++)
    {
        Historique *h = &s_historique[i];
        if (h->valide && h->sequence == sequence
            && ecoule_ms(h->t_fin_ms) < DELAI_DOUBLON_MS)
        {
            return h;
        }
    }
    return NULL;
}

static void ajouter_historique(uint8_t sequence, uint32_t transaction,
                               uint8_t resultat, uint8_t erreur)
{
    Historique *h = &s_historique[s_prochain_historique];
    h->valide      = true;
    h->sequence    = sequence;
    h->transaction = transaction;
    h->resultat    = resultat;
    h->erreur      = erreur;
    h->t_fin_ms    = HAL_GetTick();
    s_prochain_historique = (uint8_t)((s_prochain_historique + 1u) % NB_HISTORIQUE);
}

/* --- Demande en cours d'appariement -------------------------------------- */

/* Prépare la demande pour cette séquence.
 * Si une autre séquence était en attente, elle est abandonnée avec une erreur. */
static void preparer_demande(uint8_t sequence)
{
    if (s_demande.active && s_demande.sequence == sequence)
    {
        return;   /* 2e trame de la même demande */
    }
    if (s_demande.active)
    {
        envoyer_etat(s_demande.sequence, IMPR_RES_ERREUR, IMPR_ERR_TRAME_MANQUANTE);
    }
    memset(&s_demande, 0, sizeof(s_demande));
    s_demande.active     = true;
    s_demande.sequence   = sequence;
    s_demande.t_debut_ms = HAL_GetTick();
}

static void annuler_demande(uint8_t sequence)
{
    if (s_demande.active && s_demande.sequence == sequence)
    {
        s_demande.active = false;
    }
}

static bool demande_en_attente(uint8_t sequence)
{
    return s_demande.active && s_demande.sequence == sequence;
}

/* --- Impression ---------------------------------------------------------- */

/* Si les deux trames sont arrivées : compose et lance l'envoi UART (non bloquant) */
static void imprimer_si_complete(void)
{
    if (!s_demande.cmd_recue || !s_demande.date_recue)
    {
        return;   /* il manque encore une trame */
    }

    const uint8_t  seq   = s_demande.sequence;
    const uint32_t trans = s_demande.donnees.transaction;
    s_demande.active = false;   /* la demande quitte l'attente dans tous les cas */

    /* Une seule impression à la fois : le tampon est utilisé par l'envoi en cours */
    if (s_uart.en_cours)
    {
        envoyer_etat(seq, IMPR_RES_REFUSEE, IMPR_ERR_OCCUPEE);
        return;
    }

    EscPosTampon billet;
    EscPos_Init(&billet, s_memoire, sizeof(s_memoire));
    if (!Impression_ComposerBillet(&s_demande.donnees, &billet))
    {
        envoyer_etat(seq, IMPR_RES_ERREUR, IMPR_ERR_UART);
        ajouter_historique(seq, trans, IMPR_RES_ERREUR, IMPR_ERR_UART);
        return;
    }

    s_uart.fin    = false;
    s_uart.succes = false;

    /* Envoi par interruption : la fonction retourne immédiatement,
     * la fin est signalée par HAL_UART_TxCpltCallback. */
    if (HAL_UART_Transmit_IT(&UART_BILLET, s_memoire, billet.taille) != HAL_OK)
    {
        envoyer_etat(seq, IMPR_RES_ERREUR, IMPR_ERR_UART);
        ajouter_historique(seq, trans, IMPR_RES_ERREUR, IMPR_ERR_UART);
        return;
    }

    s_uart.en_cours    = true;
    s_uart.sequence    = seq;
    s_uart.transaction = trans;
    s_uart.t_debut_ms  = HAL_GetTick();
    envoyer_etat(seq, IMPR_RES_VALIDEES, IMPR_ERR_AUCUNE);
}

/* Termine l'envoi UART en cours et informe le RPi */
static void terminer_envoi(uint8_t resultat, uint8_t erreur)
{
    s_uart.en_cours = false;
    envoyer_etat(s_uart.sequence, resultat, erreur);
    ajouter_historique(s_uart.sequence, s_uart.transaction, resultat, erreur);
}

/* ========================================================================= */
/* Callbacks HAL UART (appelés en interruption)                              */
/* Si un autre module du STM32 Borne utilise un UART par interruption,       */
/* regrouper ces callbacks dans un seul fichier.                             */
/* ========================================================================= */

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == UART_BILLET.Instance)
    {
        s_uart.succes = true;
        s_uart.fin    = true;   /* lu par Impression_Task dans la boucle principale */
    }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == UART_BILLET.Instance)
    {
        s_uart.succes = false;
        s_uart.fin    = true;
    }
}

/* ========================================================================= */
/* API publique : logique T05                                                */
/* ========================================================================= */

void Impression_Init(void)
{
    memset(&s_demande, 0, sizeof(s_demande));
    memset(s_historique, 0, sizeof(s_historique));
    memset(&s_uart, 0, sizeof(s_uart));
    s_prochain_historique = 0u;
}

bool Impression_EstOccupee(void)
{
    return s_uart.en_cours;
}

void Impression_TraiterCommandeCAN(const uint8_t *data, uint8_t dlc)
{
    if (dlc == 0u)
    {
        return;   /* pas de séquence : impossible de répondre */
    }
    const uint8_t seq = data[0];

    if (dlc != 8u)
    {
        annuler_demande(seq);
        envoyer_etat(seq, IMPR_RES_REFUSEE, IMPR_ERR_DLC);
        return;
    }
    if (data[1] != 0x01u)
    {
        annuler_demande(seq);
        envoyer_etat(seq, IMPR_RES_REFUSEE, IMPR_ERR_TYPE);
        return;
    }

    DonneesBillet recu;
    Impression_DecoderCommande(data, &recu);

    if (recu.transaction > TRANSACTION_MAX)
    {
        annuler_demande(seq);
        envoyer_etat(seq, IMPR_RES_REFUSEE, IMPR_ERR_TRANSACTION);
        return;
    }
    if (recu.place < 1u || recu.place > NB_PLACES)
    {
        annuler_demande(seq);
        envoyer_etat(seq, IMPR_RES_REFUSEE, IMPR_ERR_PLACE);
        return;
    }

    /* Répétition d'une demande déjà terminée : on renvoie le dernier état, sans réimprimer */
    Historique *h = chercher_historique(seq);
    if (h != NULL && h->transaction == recu.transaction)
    {
        envoyer_etat(seq, h->resultat, h->erreur);
        return;
    }
    /* Répétition de la demande en cours d'envoi */
    if (s_uart.en_cours && s_uart.sequence == seq
        && s_uart.transaction == recu.transaction)
    {
        envoyer_etat(seq, IMPR_RES_VALIDEES, IMPR_ERR_AUCUNE);
        return;
    }
    /* 0x360 répétée alors qu'on attend encore la 0x361 */
    if (demande_en_attente(seq) && s_demande.cmd_recue)
    {
        if (s_demande.donnees.transaction != recu.transaction
            || s_demande.donnees.place != recu.place)
        {
            annuler_demande(seq);
            envoyer_etat(seq, IMPR_RES_REFUSEE, IMPR_ERR_INCOHERENCE);
        }
        return;   /* identique : simplement ignorée */
    }

    preparer_demande(seq);
    s_demande.donnees.transaction = recu.transaction;
    s_demande.donnees.place       = recu.place;
    s_demande.cmd_recue           = true;

    imprimer_si_complete();
}

void Impression_TraiterDateCAN(const uint8_t *data, uint8_t dlc)
{
    if (dlc == 0u)
    {
        return;
    }
    const uint8_t seq = data[0];

    if (dlc != 7u)
    {
        annuler_demande(seq);
        envoyer_etat(seq, IMPR_RES_REFUSEE, IMPR_ERR_DLC);
        return;
    }

    DonneesBillet recu;
    Impression_DecoderDate(data, &recu);

    if (!date_valide(&recu))
    {
        annuler_demande(seq);
        envoyer_etat(seq, IMPR_RES_REFUSEE, IMPR_ERR_DATE);
        return;
    }

    /* 0x361 répétée après la fin (ou pendant l'envoi) de sa demande : ignorée */
    if (!demande_en_attente(seq)
        && (chercher_historique(seq) != NULL
            || (s_uart.en_cours && s_uart.sequence == seq)))
    {
        return;
    }
    /* 0x361 répétée alors qu'on attend encore la 0x360 */
    if (demande_en_attente(seq) && s_demande.date_recue)
    {
        return;
    }

    preparer_demande(seq);
    s_demande.donnees.annee   = recu.annee;
    s_demande.donnees.mois    = recu.mois;
    s_demande.donnees.jour    = recu.jour;
    s_demande.donnees.heure   = recu.heure;
    s_demande.donnees.minute  = recu.minute;
    s_demande.donnees.seconde = recu.seconde;
    s_demande.date_recue      = true;

    imprimer_si_complete();
}

void Impression_Task(void)
{
    /* 1. Demande incomplète expirée */
    if (s_demande.active && ecoule_ms(s_demande.t_debut_ms) >= DELAI_APPARIEMENT_MS)
    {
        s_demande.active = false;
        envoyer_etat(s_demande.sequence, IMPR_RES_ERREUR, IMPR_ERR_TRAME_MANQUANTE);
    }

    /* 2. Fin (ou délai dépassé) de l'envoi UART */
    if (s_uart.en_cours)
    {
        if (s_uart.fin)
        {
            s_uart.fin = false;
            if (s_uart.succes)
            {
                terminer_envoi(IMPR_RES_ENVOYEE_UART, IMPR_ERR_AUCUNE);
            }
            else
            {
                terminer_envoi(IMPR_RES_ERREUR, IMPR_ERR_UART);
            }
        }
        else if (ecoule_ms(s_uart.t_debut_ms) >= DELAI_UART_MS)
        {
            HAL_UART_AbortTransmit_IT(&UART_BILLET);
            terminer_envoi(IMPR_RES_ERREUR, IMPR_ERR_DELAI_UART);
        }
    }
}

/* ========================================================================= */
/* Composition du billet (étape 2)                                           */
/* ========================================================================= */

bool Impression_ComposerBillet(const DonneesBillet *d, EscPosTampon *t)
{
    char ligne[33];      /* 32 caractères par ligne + '\0' */
    char numero[12];

    /* Place 1..14  →  "E1.1" .. "E2.7" */
    uint8_t etage = (uint8_t)(1u + (d->place - 1u) / PLACES_PAR_ETAGE);
    uint8_t rang  = (uint8_t)(1u + (d->place - 1u) % PLACES_PAR_ETAGE);

    /* Numéro toujours sur 6 chiffres : 4213 → "004213" */
    snprintf(numero, sizeof(numero), "%06lu", (unsigned long)d->transaction);

    EscPos_Reinitialiser(t);

    /* En-tête : logo centré */
    EscPos_Alignement(t, 1);
    EscPos_Image(t, LOGO_ESA, LOGO_ESA_LARGEUR_OCTETS, LOGO_ESA_HAUTEUR);
    EscPos_Ligne(t, "Eco Stationnement Automatise");
    EscPos_Ligne(t, "Cegep Limoilou");
    EscPos_Ligne(t, "--------------------------------");

    /* Détails */
    EscPos_Alignement(t, 0);
    snprintf(ligne, sizeof(ligne), "Date  : 20%02u-%02u-%02u",
             d->annee, d->mois, d->jour);
    EscPos_Ligne(t, ligne);
    snprintf(ligne, sizeof(ligne), "Heure : %02u:%02u:%02u",
             d->heure, d->minute, d->seconde);
    EscPos_Ligne(t, ligne);
    snprintf(ligne, sizeof(ligne), "Place : E%u.%u", etage, rang);
    EscPos_Ligne(t, ligne);
    EscPos_Ligne(t, TEXTE_TARIF);
    EscPos_Ligne(t, "--------------------------------");

    /* Numéro et code-barres */
    EscPos_Alignement(t, 1);
    EscPos_Ligne(t, "No de transaction");
    EscPos_Code128(t, numero, 80, 3);
    EscPos_Avancer(t, 4);

    return !t->debordement;
}

/* ========================================================================= */
/* Décodage des trames (étape 3)                                             */
/* ========================================================================= */

/* 0x360 : DB0 séquence, DB1 type, DB2..DB5 transaction (little-endian), DB6 place */
void Impression_DecoderCommande(const uint8_t *data, DonneesBillet *d)
{
    d->transaction = (uint32_t)data[2]
                   | ((uint32_t)data[3] << 8)
                   | ((uint32_t)data[4] << 16)
                   | ((uint32_t)data[5] << 24);
    d->place = data[6];
}

/* 0x361 : DB0 séquence, DB1 année depuis 2000, DB2 mois, DB3 jour,
 *         DB4 heure, DB5 minute, DB6 seconde */
void Impression_DecoderDate(const uint8_t *data, DonneesBillet *d)
{
    d->annee   = data[1];
    d->mois    = data[2];
    d->jour    = data[3];
    d->heure   = data[4];
    d->minute  = data[5];
    d->seconde = data[6];
}
