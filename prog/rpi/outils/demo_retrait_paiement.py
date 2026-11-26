#!/usr/bin/env python3
"""Banc T12 financier sur PC : T04/RFID/temps simulés, T02 réel et données jetables."""

from contextlib import ExitStack
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.borne import Borne
from exemples.facturation_retrait_simulee import FacturationRetraitSimulee
from interface.console_borne import ConsoleBorne
from modules.demande_retrait import GestionDemandeRetrait
from modules.gestion_comptes import ServiceComptes
from modules.lecteur_nfc_rfid import EvenementRFID
from stockage.comptes_csv import DepotComptesCSV

CARTE_A, CARTE_B = "0000000001", "0000000002"


class HorlogeSimulee:
    temps = 75.0

    def __call__(self):
        return self.temps


class Banc:
    def __init__(self, racine, ressources):
        self.horloge = HorlogeSimulee()
        modele = racine / "modele.csv"
        modele.write_text("id_uart,nom,solde_centimes\n"
                          f"{CARTE_A},Carte A,150\n{CARTE_B},Carte B,500\n", encoding="utf-8")
        self.comptes = ServiceComptes(DepotComptesCSV(racine / "comptes", modele))
        self.borne = Borne(self.comptes, ConsoleBorne())
        self.t04 = FacturationRetraitSimulee(self.borne, horloge=self.horloge)
        self.t04.ajouter_transaction(123456, 10, depose_a=0)
        self.t12 = GestionDemandeRetrait(self.t04, racine / "retraits.sqlite3")
        ressources.callback(self.t12.fermer)
        self.t12.autoriser_nouvelles(True)

    def commencer(self, identifiant):
        assert self.t12.demander_retrait(123456, id_demande=identifiant)
        assert self.t12.confirmer_retrait_et_figer_montant(identifiant)
        f = self.t04.consulter_retrait(identifiant).fenetre
        print(f"T12 | Montant figé : {f.montant_centimes} centimes ; fenêtre : 60 s")

    def badge(self, carte):
        if self.t04.avant_presentation():
            try:
                self.borne.traiter_evenement(EvenementRFID("ACCEPTE", "présentation simulée", carte))
            finally:
                self.t04.apres_presentation()
        else:
            print("BANC | Carte non admise : aucun débit demandé")
        self.t04.actualiser()
        self.t12.mettre_a_jour()
        print("T12 |", self.t12.obtenir_etat())

    def soldes(self):
        return tuple(self.comptes.consulter_compte(c).solde_centimes for c in (CARTE_A, CARTE_B))


def main():
    print("SIMULATION T04, RFID et horloge — aucun CAN, GPIO ni mouvement.")
    print("T02 et journaux réels dans des dossiers temporaires ; comptes actifs non utilisés.")
    with ExitStack() as ressources:
        racine = Path(ressources.enter_context(TemporaryDirectory(prefix="esa-demo-t12-")))
        for nom in ("paiement", "expiration", "interruption"):
            (racine / nom).mkdir()
        print("\n1. Carte insuffisante, puis autre carte et retransmission")
        banc = Banc(racine / "paiement", ressources)
        banc.commencer("demo-paye")
        banc.badge(CARTE_A)
        banc.badge(CARTE_B)
        banc.commencer("demo-paye")
        banc.badge(CARTE_B)
        assert banc.soldes() == (150, 300)
        assert banc.t04.gels == 1
        print("VERIFIE | Un débit intégral de 200 centimes sur B ; aucun débit sur A")

        print("\n2. Expiration exacte à 60 secondes, puis nouvelle demande")
        banc = Banc(racine / "expiration", ressources)
        banc.commencer("demo-expire")
        banc.horloge.temps += 60
        banc.badge(CARTE_B)
        assert banc.soldes() == (150, 500)
        banc.commencer("demo-nouveau")
        montant = banc.t04.consulter_retrait("demo-nouveau").fenetre.montant_centimes
        assert montant == 300
        print("VERIFIE | Aucun débit expiré ; recalcul à 300 centimes depuis le dépôt initial")

        print("\n3. Interruption pendant l'attente")
        banc = Banc(racine / "interruption", ressources)
        banc.commencer("demo-arret")
        banc.t12.arreter()
        banc.badge(CARTE_B)
        assert banc.soldes() == (150, 500)
        print("VERIFIE | Demande interrompue ; aucun paiement relancé")
    print("\nBanc financier terminé. Séquence mécanique et raccordement principal non livrés ici.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
