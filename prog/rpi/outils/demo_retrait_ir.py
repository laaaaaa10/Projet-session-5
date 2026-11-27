#!/usr/bin/env python3
"""Lecture IR de T12 après attente de paiement : banc uniquement, aucun matériel."""
import argparse
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

RPI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RPI), str(RPI.parent)]

from application.integration_t12 import RaccordementRetrait, LecteurGardeRetrait
from commun.t13.protocole import nouvelle_commande
from exemples.banc_retrait import BancRetrait, CARTE
from exemples.service_retrait_simule import ServiceRetraitSimule
from modules.lecteur_nfc_rfid import EvenementRFID
from modules.service_t13 import GestionServiceT13
from modules.stationnement import EtatPlace


def executer(scenario):
    print('SIMULATION : CAN, STM32, T04, IR, sécurité, RFID et horloge. Aucun matériel.')
    print('Vraies machines T12/T11/T13, raccordement applicatif et vrai T02 sur comptes temporaires.')
    with TemporaryDirectory(prefix='esa-t12-lecture-ir-') as dossier:
        b = BancRetrait(dossier)
        service = GestionServiceT13(ServiceRetraitSimule(b), Path(dossier) / 'service.sqlite3', horloge=b.horloge)
        application = RaccordementRetrait(b.t12, t04=b.t04, etat_service=lambda: service.etat)
        try:
            service.traiter(nouvelle_commande('REMETTRE_EN_SERVICE'))
            assert application.demander(123456, 'demo-ir').phase == 'DEMANDE'
            assert application.confirmer('demo-ir').phase == 'VERIFICATION_IR'
            assert b.t04.gels == 0
            print('AVANT PAIEMENT | CAN 0x302 [FF] ; attente des états 0x301 et 0x311')
            application.actualiser()
            assert application.vue().phase == 'ATTENTE_PAIEMENT'
            assert b.t04.gels == 1
            print('T04 simulé | Montant figé : 200 centimes ; fenêtre de 60 secondes ouverte')
            for _ in range(60):
                b.tour(.5)
                service.actualiser()
                application.actualiser()
            assert application.vue().phase == 'ATTENTE_PAIEMENT'
            assert b.horloge() - b.t12._places[10][1] >= 30
            print('ATTENTE | 30 secondes écoulées ; les états IR précédents sont périmés')
            if scenario == 'muet':
                b.can.repondre_lecture_ir = False
            lecteur = SimpleNamespace(lire=lambda: [EvenementRFID('ACCEPTE', 'badge simulé', CARTE)])
            b.borne.actualiser(LecteurGardeRetrait(lecteur, application), t04=b.t04)
            application.actualiser()
            assert application.vue().phase == 'VERIFICATION_IR_APRES_PAIEMENT'
            assert b.can.envoyees == [(0x302, bytes([0xFF]))] * 2
            assert b.comptes.consulter_compte(CARTE).solde_centimes == 800
            print('APRÈS PAIEMENT | Nouvelle lecture 0x302 [FF] ; aucune commande d’actionneur')
            if scenario == 'muet':
                b.tour(1)
                application.actualiser()
                service.actualiser()
                assert application.vue().phase == 'INTERROMPU'
                assert service.etat == 'ARRET_VERROUILLE'
                assert b.t04.nombre_clotures == 0 and b.modele.etat(10) == EtatPlace.OCCUPEE
                avant = list(b.can.envoyees)
                b.can.synchroniser_ir()  # réponse volontairement trop tardive
                application.actualiser()
                assert b.can.envoyees == avant
                assert not any(i in (0x100, 0x110, 0x120) for i, _ in b.can.envoyees)
                print('VÉRIFIÉ | États manquants -> arrêt ; réponse tardive ignorée ; aucun mouvement ni clôture')
            else:
                application.actualiser()
                assert application.vue().phase == 'PREPARATION'
                service.traiter(nouvelle_commande('METTRE_HORS_SERVICE'))
                for _ in range(35):
                    if application.vue().phase == 'ATTENTE_RETRAIT_MANUEL':
                        break
                    b.mouvement(); application.actualiser(); service.actualiser()
                assert application.vue().phase == 'ATTENTE_RETRAIT_MANUEL'
                assert b.t04.nombre_clotures == 0 and service.etat == 'MISE_HORS_SERVICE'
                print('T12 | Mécanique simulée terminée ; attente du retrait manuel')
                b.can.ir_sortie(False)
                application.actualiser(); service.actualiser()
                assert application.vue().phase == 'TERMINE'
                assert b.t04.nombre_clotures == 1 and service.etat == 'HORS_SERVICE'
                print('VÉRIFIÉ | États frais avant départ, retrait manuel puis clôture unique')
            print(f'FIN | T12={application.vue().phase}, T13={service.etat}, clôtures={b.t04.nombre_clotures}')
        finally:
            application.fermer()
            service.fermer()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=('nominal', 'muet'), default='nominal')
    executer(parser.parse_args().scenario)


if __name__ == '__main__':
    main()
