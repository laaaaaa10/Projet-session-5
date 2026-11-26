#!/usr/bin/env python3
"""Démonstration T12 reproductible sur PC, sans broker ni matériel."""
import argparse
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

RPI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RPI), str(RPI.parent)]

from commun.t13.protocole import nouvelle_commande
from exemples.banc_retrait import BancRetrait, CARTE
from exemples.service_retrait_simule import ServiceRetraitSimule
from modules.retrait import EtapeRetrait as E
from modules.service_t13 import GestionServiceT13
from modules.stationnement import EtatPlace


def executer(scenario):
    print('SIMULATION : CAN, STM32, T04, IR, barrière, RFID et horloge.')
    print('Vraies machines T12/T11/T13 et vrai T02 sur des données temporaires. Aucun matériel.')
    with TemporaryDirectory(prefix='esa-demo-retrait-') as dossier:
        b = BancRetrait(dossier)
        adaptateur = ServiceRetraitSimule(b)
        service = GestionServiceT13(adaptateur, Path(dossier) / 'service.sqlite3', horloge=b.horloge)
        try:
            def ordre(action):
                resultat = service.traiter(nouvelle_commande(action))
                print(f'T13 | {action} -> {service.etat} ({resultat[-1]["phase"]})')
            ordre('REMETTRE_EN_SERVICE')
            b.payer()
            print('T02 | Paiement intégral : 200 centimes, une seule carte simulée')
            if scenario == 'ir-muet':
                b.can.ir_place_actif = False
            assert b.t12.autoriser_apres_paiement('retrait-1')
            if scenario == 'nominal':
                ordre('METTRE_HORS_SERVICE')
            for _ in range(30):
                if b.t12.etape in (E.ATTENTE_MANUEL, E.ATTENTE_PLACE, E.DEFAUT, E.INTERROMPU):
                    break
                if scenario == 'arret' and b.t12.etape == E.ACCES:
                    ordre('ARRET_IMMEDIAT')
                    break
                c = b.t12._cmd
                if c:
                    print(f'CAN simulé | {b.t12.etape.value}: 0x{c.identifiant:03X} action={c.action} cible={c.cible}')
                b.mouvement()
                service.actualiser()
            if scenario == 'nominal':
                assert b.t12.etape == E.ATTENTE_MANUEL
                assert b.t04.nombre_clotures == 0 and b.modele.etat(10) == EtatPlace.OCCUPEE
                print('T12 | Présence sortie confirmée ; attente du retrait manuel ; place logique encore occupée')
                assert not b.t11.demarrer(654321, 1, 1)
                print('BANC | Injection du départ manuel simulé : IR sortie -> absence')
                b.can.ir_sortie(False)
                b.tour()
                service.actualiser()
                assert b.t12.etape == E.TERMINE and b.t04.nombre_clotures == 1
                assert service.etat == 'HORS_SERVICE'
                avant = list(b.can.envoyees)
                assert b.t12.autoriser_apres_paiement('retrait-1')
                b.tour()
                assert b.can.envoyees == avant and b.t04.nombre_clotures == 1
                print('VÉRIFIÉ | Clôture unique T04 simulé, place libre, retour niveau 0/angle 0, aucun rejeu')
            elif scenario == 'ir-muet':
                assert b.t12.etape == E.ATTENTE_PLACE
                b.tour(5.1)
                service.actualiser()
                assert b.t12.etape == E.DEFAUT and service.etat == 'ARRET_VERROUILLE'
                assert b.t04.nombre_clotures == 0 and b.modele.etat(10) == EtatPlace.OCCUPEE
                print('VÉRIFIÉ | Absence IR manquante -> arrêt verrouillé ; ni transport sortie ni clôture')
            else:
                assert b.t12.etape == E.INTERROMPU
                avant = list(b.can.envoyees)
                adaptateur.intervention_simulee()
                ordre('REINITIALISER')
                b.tour(.6)
                service.actualiser()
                assert service.etat == 'HORS_SERVICE' and b.can.envoyees == avant
                assert b.t12.etape == E.INTERROMPU
                print('VÉRIFIÉ | Réinitialisation -> HORS_SERVICE ; transaction interrompue à résoudre ; aucun mouvement relancé')
            assert b.comptes.consulter_compte(CARTE).solde_centimes == 800
            print(f'FIN | T12={b.t12.obtenir_etat()}, T13={service.etat}, clôtures={b.t04.nombre_clotures}')
        finally:
            service.fermer()
            b.fermer()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=('nominal', 'ir-muet', 'arret'), default='nominal')
    executer(parser.parse_args().scenario)


if __name__ == '__main__':
    main()
