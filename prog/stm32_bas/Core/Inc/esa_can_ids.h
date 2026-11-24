/*
 * esa_can_ids.h
 *
 *  Created on: 24 nov. 2026
 *      Author: William MacDonald
 *
 * Identifiants CAN du projet ESA (Protocole CAN 243-557 A2026 v1.6, section 3).
 * Trames standard 11 bits, entiers multioctets en little-endian.
 */

#ifndef INC_ESA_CAN_IDS_H_
#define INC_ESA_CAN_IDS_H_

/* Arrêts, défauts, surveillance */
#define CAN_ID_ARRET_HAUT              0x001u
#define CAN_ID_ARRET_BAS               0x002u
#define CAN_ID_ARRET_BORNE             0x003u
#define CAN_ID_ARRET_RPI               0x004u
#define CAN_ID_DEFAUT_HAUT             0x010u
#define CAN_ID_DEFAUT_BAS              0x011u
#define CAN_ID_DEFAUT_BORNE            0x012u
#define CAN_ID_DEFAUT_RPI              0x013u
#define CAN_ID_HEARTBEAT_RPI           0x040u
#define CAN_ID_HEARTBEAT_HAUT          0x041u
#define CAN_ID_HEARTBEAT_BAS           0x042u
#define CAN_ID_HEARTBEAT_BORNE         0x043u
#define CAN_ID_REARMEMENT_CMD          0x050u
#define CAN_ID_REARMEMENT_HAUT         0x051u
#define CAN_ID_REARMEMENT_BAS          0x052u
#define CAN_ID_REARMEMENT_BORNE        0x053u
#define CAN_ID_SYNCHRO_CMD             0x080u

/* Mouvements */
#define CAN_ID_ELEVATION_CMD           0x100u
#define CAN_ID_ROTATION_CMD            0x110u
#define CAN_ID_BRAS_CMD                0x120u
#define CAN_ID_ELEVATION_ETAT          0x200u
#define CAN_ID_ROTATION_ETAT           0x210u
#define CAN_ID_BRAS_ETAT               0x220u

/* Impression */
#define CAN_ID_IMPRESSION_ETAT         0x230u
#define CAN_ID_IMPRESSION_CMD          0x360u
#define CAN_ID_IMPRESSION_DATE         0x361u

/* Détection IR (T06) */
#define CAN_ID_IR_BAS_CHANGEMENT       0x300u
#define CAN_ID_IR_BAS_COMPLET          0x301u
#define CAN_ID_IR_LECTURE_CMD          0x302u
#define CAN_ID_IR_ENTREE_CHANGEMENT    0x310u
#define CAN_ID_IR_ENTREE_COMPLET       0x311u

/* Luminosité, étages */
#define CAN_ID_LUMINOSITE_ETAT         0x320u
#define CAN_ID_ETAGE_DETECTE           0x330u
#define CAN_ID_ETAGE_ETAT              0x331u
#define CAN_ID_ETAGE_LECTURE_CMD       0x332u

/* DEL et éclairage (T07) */
#define CAN_ID_ECLAIRAGE_CMD           0x130u
#define CAN_ID_DEL_PLACE_CMD           0x340u
#define CAN_ID_DEL_BAS_ETAT            0x341u
#define CAN_ID_DEL_HAUT_ETAT           0x342u
#define CAN_ID_ECLAIRAGE_BAS_ETAT      0x350u
#define CAN_ID_ECLAIRAGE_HAUT_ETAT     0x351u
#define CAN_ID_ECLAIRAGE_BORNE_ETAT    0x352u

/* État des heartbeats (DB1) */
#define HEARTBEAT_ETAT_INITIALISATION  0u
#define HEARTBEAT_ETAT_PRET            1u
#define HEARTBEAT_ETAT_OCCUPE          2u
#define HEARTBEAT_ETAT_ARRET_VERROUILLE 3u
#define HEARTBEAT_ETAT_DEFAUT          4u

#endif /* INC_ESA_CAN_IDS_H_ */
