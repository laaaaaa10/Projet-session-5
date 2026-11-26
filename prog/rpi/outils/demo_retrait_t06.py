#!/usr/bin/env python3
"""T12 ↔ code C T06 Bas sur PC Linux ; aucun matériel, T04 et Haut simulés."""
import argparse
from functools import partial
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

RPI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RPI), str(RPI.parent)]

from application.integration_t12 import RaccordementRetrait, LecteurGardeRetrait
from commun.t13.protocole import nouvelle_commande
from exemples.banc_retrait import BancRetrait, CARTE
from exemples.banc_retrait_t06 import SOURCE_T06, compiler_t06, BusRetraitCodeT06
from exemples.service_retrait_simule import ServiceRetraitSimule
from modules.lecteur_nfc_rfid import EvenementRFID
from modules.service_t13 import GestionServiceT13
from modules.stationnement import EtatPlace


def executer(scenario):
    print('CODE EXÉCUTÉ : T12/T11/T13/T02 et t06_ir.c du STM32 Bas compilé pour ce PC.')
    print('SIMULATION : PCB-04, Haut/rampe, moteurs, CAN, sécurité, T04, RFID et horloge.')
    print('Aucun matériel ; aucun raccordement réel activé.')
    print(f'SOURCE T06 | SHA-256 {sha256(SOURCE_T06.read_bytes()).hexdigest()}')
    with TemporaryDirectory(prefix='esa-t12-t06-') as dossier:
        bibliotheque = compiler_t06(dossier)
        b = BancRetrait(dossier, fabrique_can=partial(BusRetraitCodeT06, bibliotheque=bibliotheque))
        service = GestionServiceT13(ServiceRetraitSimule(b), Path(dossier) / 'service.sqlite3', horloge=b.horloge)
        app = RaccordementRetrait(b.t12, t04=b.t04, etat_service=lambda: service.etat)
        trace_lue = 0

        def trace():
            nonlocal trace_lue
            for _, ident, donnees in b.can.trace_bas[trace_lue:]:
                print(f'T06 BAS compilé | 0x{ident:03X} [{donnees.hex(" ")}]')
            trace_lue = len(b.can.trace_bas)

        try:
            service.traiter(nouvelle_commande('REMETTRE_EN_SERVICE'))
            if scenario == 'haut-absent':
                b.can.haut_actif = False
                print('INJECTION | Détecteur Haut muet ; heartbeats simulés maintenus')
            assert app.demander(123456, 'demo-t06').phase == 'DEMANDE'
            assert app.confirmer('demo-t06').phase == 'VERIFICATION_IR'
            assert b.t04.gels == 0
            app.actualiser()
            trace()
            if scenario == 'haut-absent':
                assert b.t12.lecture_ir.reponses == {0x301}
                b.tour(1)
                app.actualiser(); service.actualiser()
                assert app.vue().phase == 'INTERROMPU' and service.etat == 'ARRET_VERROUILLE'
                assert b.t04.gels == 0 and b.comptes.consulter_compte(CARTE).solde_centimes == 1000
                avant = list(b.can.envoyees)
                b.can.haut_actif = True
                b.can.synchroniser_ir()
                app.actualiser()
                assert b.can.envoyees == avant and b.t04.gels == 0
                assert not any(i in (0x100, 0x110, 0x120) for i, _ in b.can.envoyees)
                print('VÉRIFIÉ | 0x311 absent : aucun gel, aucun débit, aucun mouvement ; réponse tardive sans reprise')
            else:
                assert app.vue().phase == 'ATTENTE_PAIEMENT' and b.t04.gels == 1
                for _ in range(60):
                    b.tour(.5); app.actualiser(); service.actualiser()
                print('PAIEMENT | 30 s simulées ; débit T02 de 200 centimes via T04 simulé')
                lecteur = SimpleNamespace(lire=lambda: [EvenementRFID('ACCEPTE', 'badge simulé', CARTE)])
                b.borne.actualiser(LecteurGardeRetrait(lecteur, app), t04=b.t04)
                app.actualiser()
                assert app.vue().phase == 'VERIFICATION_IR_APRES_PAIEMENT'
                assert b.comptes.consulter_compte(CARTE).solde_centimes == 800
                assert b.can.envoyees == [(0x302, bytes([0xFF]))] * 2
                trace()
                app.actualiser()
                assert app.vue().phase == 'PREPARATION'
                service.traiter(nouvelle_commande('METTRE_HORS_SERVICE'))
                for _ in range(40):
                    if app.vue().phase == 'ATTENTE_RETRAIT_MANUEL':
                        break
                    b.mouvement(); app.actualiser(); service.actualiser(); trace()
                assert app.vue().phase == 'ATTENTE_RETRAIT_MANUEL'
                assert b.modele.etat(10) == EtatPlace.OCCUPEE and b.t04.nombre_clotures == 0
                print('T12 | Place 10 physiquement vide selon T06 C ; attente du départ de la rampe simulée')
                b.can.ir_sortie(False)
                app.actualiser(); service.actualiser()
                assert app.vue().phase == 'TERMINE' and service.etat == 'HORS_SERVICE'
                assert b.modele.etat(10) == EtatPlace.LIBRE and b.t04.nombre_clotures == 1
                print('VÉRIFIÉ | Départ manuel simulé puis clôture unique T04 simulé')
            print(f'FIN | T12={app.vue().phase}, T13={service.etat}, clôtures={b.t04.nombre_clotures}')
        finally:
            app.fermer()
            service.fermer()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=('nominal', 'haut-absent'), default='nominal')
    executer(parser.parse_args().scenario)


if __name__ == '__main__':
    main()
