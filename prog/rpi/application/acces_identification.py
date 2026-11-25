"""Adapte T02 pour T03 : une file de lectures distincte des resultats T04."""

from threading import Lock

from modeles.comptes import Compte, IdentificationCarte
from modules.gestion_comptes import ServiceComptes


class AccesIdentification:
    def __init__(self, comptes: ServiceComptes):
        self._comptes = comptes
        self._lectures: list[IdentificationCarte] = []
        self._verrou = Lock()

    def consulter_solde(self, id_uart: str) -> int | None:
        compte = self._comptes.consulter_compte(id_uart)
        return None if compte is None else compte.solde_centimes

    def lire_identifications(self) -> list[IdentificationCarte]:
        with self._verrou:
            lectures, self._lectures = self._lectures, []
            return lectures

    def _publier(self, id_uart: str, compte: Compte | None) -> None:
        """Appel interne de la borne uniquement, apres validation RFID et lookup."""
        lecture = IdentificationCarte(id_uart, None if compte is None else compte.solde_centimes)
        with self._verrou:
            self._lectures.append(lecture)
