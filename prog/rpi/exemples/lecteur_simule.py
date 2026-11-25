"""Lectures logiques de demonstration ; ne simule ni l'electronique ni le checksum."""

from modules.lecteur_nfc_rfid import EvenementRFID
from modeles.comptes import valider_id_uart


class LecteurSimule:
    def __init__(self):
        self.ouvert = False
        self._evenements = []

    def ouvrir(self):
        self.ouvert = True
        self._evenements = [EvenementRFID("INFO", "Lecteur simule : chaque clic represente une presentation.")]
        return self

    def simuler(self, id_uart):
        if not self.ouvert:
            raise RuntimeError("Lecteur simule ferme")
        self._evenements.append(EvenementRFID("ACCEPTE", "presentation simulee", valider_id_uart(id_uart)))

    def lire(self):
        if not self.ouvert:
            raise RuntimeError("Lecteur simule ferme")
        evenements, self._evenements = self._evenements, []
        return evenements

    def fermer(self):
        self.ouvert = False
        self._evenements.clear()
