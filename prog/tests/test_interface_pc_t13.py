"""Selection et renvoi dans le vrai Qt ; pont reseau simule dans cette suite."""

from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PyQt6.QtCore import QItemSelectionModel, QObject, Qt, pyqtSignal
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    from pc.interface import FenetreSupervision
    QT_DISPONIBLE = True
except ModuleNotFoundError as erreur:
    if erreur.name != "PyQt6":
        raise
    QT_DISPONIBLE = False


if QT_DISPONIBLE:
    class PontSimule(QObject):
        vue = pyqtSignal(object)
        erreur = pyqtSignal(str)
        termine = pyqtSignal()
        requete = pyqtSignal(str, object)
        arret = pyqtSignal()


def demande(lettre):
    return {"demande": {"id_commande": "t13:credit-" + lettre * 32,
                        "commande": "AJOUTER_CREDIT",
                        "parametres": {"id_uart": "11008827F9", "montant_centimes": 500}},
            "termine": True,
            "reponse": {"phase": "TERMINEE", "code": "CREDITE", "donnees": {}}}


@unittest.skipUnless(QT_DISPONIBLE, "PyQt6 absent : aucune validation graphique")
class TestsSelectionPC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.pont = PontSimule()
        self.fenetre = FenetreSupervision(self.pont)
        self.pont.arret.connect(self.pont.termine.emit)
        self.addCleanup(self.fenetre.close)
        self.requetes = []
        self.pont.requete.connect(lambda action, params: self.requetes.append((action, params)))
        self.vue = {"statut": "A_JOUR", "etat": {"disponibilite": {"T02": True}},
                    "demandes": [demande("a"), demande("b")]}
        self.fenetre.actualiser(self.vue)
        self.fenetre.show()
        self.app.processEvents()

    def cliquer_ligne(self, ligne):
        table = self.fenetre.demandes
        rectangle = table.visualItemRect(table.item(ligne, 1))
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())

    def test_selection_sans_cellule_courante_conserve_le_bon_id(self):
        table = self.fenetre.demandes
        selection = table.selectionModel()
        selection.clearCurrentIndex()
        # Qt distingue la selection et l'index courant : une ligne peut etre
        # selectionnee sans deplacer ce dernier (en-tete, selection externe).
        selection.select(table.model().index(1, 0),
                         QItemSelectionModel.SelectionFlag.ClearAndSelect
                         | QItemSelectionModel.SelectionFlag.Rows)
        self.fenetre.actualiser(self.vue)
        self.assertTrue(self.fenetre.reprendre.isEnabled())
        self.assertEqual([i.row() for i in selection.selectedRows()], [1])
        self.fenetre.reprendre.click()
        self.assertEqual(self.requetes, [("REPRENDRE_DEMANDE",
                                         {"id_commande": "t13:credit-" + "b" * 32})])

    def test_clic_active_immediatement_et_nouvelle_ligne_preserve_id(self):
        self.cliquer_ligne(1)
        self.assertTrue(self.fenetre.reprendre.isEnabled())
        vue = deepcopy(self.vue)
        vue["demandes"].insert(0, demande("c"))
        for _ in range(5):
            self.fenetre.actualiser(vue)
            self.app.processEvents()
        table = self.fenetre.demandes
        self.assertEqual([i.row() for i in table.selectionModel().selectedRows()], [2])
        self.fenetre.reprendre.click()
        self.assertEqual(self.requetes, [("REPRENDRE_DEMANDE",
                                         {"id_commande": "t13:credit-" + "b" * 32})])

    def test_aucun_renvoi_sans_selection_donnees_fraiches_ou_apres_arret(self):
        self.cliquer_ligne(0)
        self.fenetre.actualiser(self.vue)
        self.fenetre.demandes.clearSelection()
        self.assertFalse(self.fenetre.reprendre.isEnabled())
        self.cliquer_ligne(0)
        vue = dict(self.vue, statut="PERIMEES")
        self.fenetre.actualiser(vue)
        self.assertFalse(self.fenetre.reprendre.isEnabled())
        self.fenetre.reprendre.click()
        self.assertEqual(self.requetes, [])
        self.fenetre.actualiser(self.vue)
        self.assertTrue(self.fenetre.reprendre.isEnabled())
        self.pont.termine.emit()
        self.cliquer_ligne(1)
        self.assertFalse(self.fenetre.reprendre.isEnabled())


if __name__ == "__main__":
    unittest.main()
