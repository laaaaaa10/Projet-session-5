"""
evenements.py

T01 - Crochets pour les tâches qui n'ont pas encore de module ou de page
(T04 au retrait, T12, T13, radar) et signaux vers les autres tâches.

Entrées : les modules appellent les crochets depuis n'importe quel thread
(réception du ServiceCAN, lecteur, MQTT) ; le signal Qt ramène l'appel dans
le thread de l'écran. Exemple avec le bus CAN commun :
    services.can.abonner([0x001, 0x002, 0x003, 0x004],
                         lambda identifiant, donnees: ecran.evenements.etat_service(False, "Arrêt"))

Sorties : les modules se branchent sur les signaux. Les fonctions branchées
s'exécutent dans le thread de l'écran : elles ne doivent pas bloquer.

 Created on: 25 nov. 2026
      Author: Javier Bolduc
"""

from PyQt6.QtCore import QObject, pyqtSignal

# Valeurs acceptées par etat_operation()
ETAT_EN_COURS = "en_cours"
ETAT_TERMINE = "termine"
ETAT_ERREUR = "erreur"


class EvenementsBorne(QObject):
    """Point de branchement unique de l'écran avec les tâches non livrées."""

    # --- Signaux internes (crochets d'entrée -> contrôleur) -----------------
    sig_resultat_retrait = pyqtSignal(bool, str)
    sig_etat_operation = pyqtSignal(str, str)
    sig_etat_service = pyqtSignal(bool, str)
    sig_presence_usager = pyqtSignal(bool)

    # --- Signaux de sortie (écran -> autres tâches) --------------------------
    billet_confirme = pyqtSignal(int, int)    # (transaction, place 1-14) -> T03 : barrière, puis T11
    retrait_demande = pyqtSignal(int)         # numéro du billet -> T04 : vérifier, puis paiement T02
    operation_annulee = pyqtSignal()          # l'usager a annulé ou le délai est dépassé

    # --- Crochets d'entrée ---------------------------------------------------

    def resultat_retrait(self, trouve, message=""):
        """T04 : réponse à retrait_demande. Si trouve, T04 demande ensuite le
        paiement au pont T02 (affiché par l'écran)."""
        self.sig_resultat_retrait.emit(bool(trouve), str(message))

    def etat_operation(self, etat, message=""):
        """T12 (récupération) : ETAT_EN_COURS, ETAT_TERMINE ou ETAT_ERREUR.
        Le dépôt (T11) est suivi directement par l'écran."""
        self.sig_etat_operation.emit(str(etat), str(message))

    def etat_service(self, en_service, message=""):
        """T13 / arrêts CAN : borne en service ou hors service."""
        self.sig_etat_service.emit(bool(en_service), str(message))

    def presence_usager(self, present):
        """Radar : un usager est présent ou non devant la borne."""
        self.sig_presence_usager.emit(bool(present))
