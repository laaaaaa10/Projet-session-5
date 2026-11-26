"""
services.py

T01 - Objets partagés de la borne, créés une seule fois pour toute l'application :

  can          ServiceCAN unique (can0, ou bus virtuel avec --simulation)
  modele       ModeleStationnement des 14 places
  pont_t02     PontT02Qt : lecteur RFID et comptes (T02)
  reservation  GestionReservation (T03)
  billets      GestionBillets (T05, CAN)
  depot        GestionDepot (T11, CAN)

Ajouter un module CAN (T06, T12...) : le créer ici avec self.can, comme T05
et T11. Aucun module n'ouvre son propre bus.

 Created on: 26 nov. 2026
      Author: Javier Bolduc
"""

from tempfile import TemporaryDirectory

from communications.can_bus import ServiceCAN
from interface.qt.pont_t02 import PontT02Qt
from interface.src.hardware import raccordements
from modules.billets import creer_gestion_billets
from modules.depot import creer_gestion_depot
from modules.reservation import GestionReservation
from modules.stationnement import NB_PLACES, ModeleStationnement, Presence
from stockage.comptes_csv import DOSSIER_ACTIF

CANAL_SIMULATION = "esa"


class Services:

    def __init__(self, simulation=False, options_lecteur=None, dossier_donnees=DOSSIER_ACTIF):
        """simulation : bus CAN virtuel, STM32 simulés, lecteur RFID simulé et
        copie temporaire des comptes (essais sur PC, aucun matériel)."""
        self.simulation = simulation
        self.cartes = {}                 # session T03 -> carte acceptée (pour T04)
        self.erreur_can = ""             # raison si le bus n'a pas pu être ouvert
        self._simulateurs = []
        self._donnees_temp = None

        if simulation:
            self._donnees_temp = TemporaryDirectory(prefix="esa-t01-")
            dossier_donnees = self._donnees_temp.name
            self.can = ServiceCAN(interface="virtual", channel=CANAL_SIMULATION)
        else:
            self.can = ServiceCAN()

        self.modele = ModeleStationnement()
        if simulation:                   # T06 simulé : aucune voiture dans les places
            for numero in range(1, NB_PLACES + 1):
                self.modele.changer_presence(numero, Presence.ABSENT)

        self.pont_t02 = PontT02Qt(dossier_donnees, simulation=simulation,
                                  options_lecteur=options_lecteur)
        self.reservation = GestionReservation(self.modele, self._creer_transaction,
                                              raccordements.conditions_confirmation)
        self.billets = creer_gestion_billets(self.can)
        self.depot = creer_gestion_depot(self.can, self.modele, raccordements.facturation)

    def demarrer(self):
        """Ouvre le bus CAN puis le lecteur RFID. Sans bus, la borne reste utilisable
        (le billet affiche « impression impossible »)."""
        if self.simulation:
            from exemples.simulateur_ascenseur import SimulateurAscenseur
            from exemples.simulateur_stm32_borne import SimulateurStm32Borne
            self._simulateurs = [SimulateurStm32Borne(channel=CANAL_SIMULATION),
                                 SimulateurAscenseur(channel=CANAL_SIMULATION)]
        try:
            self.can.demarrer()
            for simulateur in self._simulateurs:
                simulateur.demarrer()
        except Exception as erreur:
            self.erreur_can = str(erreur)
        self.pont_t02.demarrer()

    def mettre_a_jour(self):
        """Délais de T11 : à appeler périodiquement."""
        self.depot.mettre_a_jour()

    def arreter(self):
        """Libère le matériel. Le pont T02 doit déjà être arrêté (signal arrete)."""
        self.depot.arreter()
        self.can.arreter()
        for simulateur in self._simulateurs:
            simulateur.arreter()
        if self._donnees_temp is not None:
            self._donnees_temp.cleanup()

    def _creer_transaction(self, numero_place, id_session):
        # T03 donne la session ; T04 reçoit la carte acceptée pour cette session
        return raccordements.creer_transaction(numero_place, self.cartes.get(id_session))
