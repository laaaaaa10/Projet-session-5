"""Parcours opérateur dans la vraie fenêtre Qt, sans réseau ni matériel."""

from copy import deepcopy
from unittest.mock import Mock, patch
import unittest

from test_interface_pc_t13 import QT_DISPONIBLE, demande

if QT_DISPONIBLE:
    from test_interface_pc_t13 import PontSimule
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QPushButton
    from commun.t13.configuration import ConfigurationMQTT
    from pc.interface import FenetreSupervision
    from pc.main import main


def vue_initiale():
    return {"statut": "A_JOUR", "demandes": [], "etat": {
        "session": "banc-qt", "revision": 1,
        "etat_service": "HORS_SERVICE", "service_simule": True,
        "places": [{"id": f"E{n}.{p}", "logique": "INCONNU", "presence": None}
                   for n in (1, 2) for p in range(1, 8)],
        "soldes": {"1100823734": 2000, "11008827F9": 2500},
        "anomalies": [], "transactions": None, "statistiques": None,
        "disponibilite": {"T02": True, "service": True},
    }}


@unittest.skipUnless(QT_DISPONIBLE, "PyQt6 absent : aucune validation graphique")
class TestsConsolePC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.pont = PontSimule()
        self.pont.arret.connect(self.pont.termine.emit)
        self.fenetre = FenetreSupervision(self.pont)
        self.addCleanup(self.fenetre.close)
        self.vue = vue_initiale()
        self.requetes = []
        self.pont.requete.connect(lambda action, params: self.requetes.append((action, params)))
        self.fenetre.actualiser(self.vue)
        self.fenetre.show()
        self.app.processEvents()

    def test_places_inconnues_et_presence_distincte_du_statut_logique(self):
        f = self.fenetre
        self.assertEqual(f.compteurs["LIBRE"].text(), "—")
        self.assertEqual(f.compteurs["INCONNU"].text(), "14")
        self.vue["etat"]["places"][0].update(logique="réservée", presence="présent")
        self.vue["etat"]["places"][1].update(logique="libre", presence=False)
        f.actualiser(self.vue)
        self.assertEqual(f.compteurs["LIBRE"].text(), "1")
        self.assertEqual(f.compteurs["RESERVEE"].text(), "1")
        self.assertEqual(f.compteurs["INCONNU"].text(), "12")
        self.assertEqual(f.places["E1.1"].logique.text(), "Réservée")
        self.assertEqual(f.places["E1.1"].presence.text(), "IR : présent")
        self.assertEqual(f.places["E1.2"].presence.text(), "IR : absent")
        self.assertEqual(f.places["E1.3"].presence.text(), "IR : inconnu")
        f.actualiser(dict(self.vue, statut="PERIMEES"))
        self.assertEqual(f.places["E1.1"].property("ton"), "neutre")
        self.assertIn("PÉRIMÉES", f.origine_etat.text())

    def test_selection_carte_filtre_et_actualisation_conservent_la_saisie(self):
        f = self.fenetre
        f.afficher_page(1)
        self.app.processEvents()
        rectangle = f.comptes.visualItemRect(f.comptes.item(1, 0))
        QTest.mouseClick(f.comptes.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
        self.assertEqual(f.carte.text(), "11008827F9")
        self.assertEqual(f.solde_selectionne.text(), "2 500 ¢")
        self.vue["etat"]["soldes"]["11008827F9"] = 3000
        f.actualiser(self.vue)
        self.assertEqual(f.carte.text(), "11008827F9")
        self.assertEqual(f.solde_selectionne.text(), "3 000 ¢")
        self.assertEqual(len(f.comptes.selectionModel().selectedRows()), 1)
        f.recherche_comptes.setText("827f9")
        self.assertEqual(f.comptes.rowCount(), 1)
        self.assertEqual(f.comptes.item(0, 0).text(), "11008827F9")

    def test_identifiant_et_credit_double_clic_avec_vue_ancienne(self):
        f = self.fenetre
        f.carte.setText("pasvalide!")
        self.assertFalse(f.consulter.isEnabled())
        f.crediter.click()
        self.assertEqual(self.requetes, [])
        f.carte.setText("11008827F9A")
        self.assertFalse(f.crediter.isEnabled())
        f.carte.setText("11008827f9")
        f.montant.setValue(525)
        f.crediter.click()
        # Le prochain instantané peut précéder l'insertion dans le journal.
        f.actualiser(self.vue)
        f.crediter.click()
        self.assertEqual(self.requetes, [("AJOUTER_CREDIT", {
            "id_uart": "11008827F9", "montant_centimes": 525})])
        nouvelle = deepcopy(self.vue)
        entree = demande("c")
        entree.update(termine=False, reponse=None)
        nouvelle["demandes"] = [entree]
        f.actualiser(nouvelle)
        self.assertFalse(f.crediter.isEnabled())
        entree.update(termine=True, reponse={"phase": "TERMINEE", "code": "CREDITE", "donnees": {}})
        f.actualiser(nouvelle)
        self.assertTrue(f.crediter.isEnabled())
        self.assertIn("Crédit ajouté", f.resultat_compte.text())

    def test_coupure_interdit_envoi_et_laisse_consulter_les_pages(self):
        f = self.fenetre
        f.carte.setText("11008827F9")
        for statut in ("PERIMEES", "DECONNECTE"):
            f.actualiser(dict(self.vue, statut=statut))
            for index, bouton in enumerate(f.navigation):
                bouton.click()
                self.assertEqual(f.pages.currentIndex(), index)
                for commande in f.commandes_service.values():
                    self.assertFalse(commande.isEnabled())
                    commande.click()
            self.assertFalse(f.consulter.isEnabled())
            self.assertFalse(f.crediter.isEnabled())
        self.assertEqual(self.requetes, [])
        f.actualiser(self.vue)
        self.assertTrue(f.crediter.isEnabled())

    def test_acceptation_reste_en_cours_et_donnees_indisponibles_restent_vides(self):
        f = self.fenetre
        entree = demande("a")
        entree.update(termine=False, reponse={"phase": "ACCEPTEE", "code": "TRANSACTION_A_TERMINER", "donnees": {}})
        self.vue["demandes"] = [entree]
        f.actualiser(self.vue)
        self.assertIn("En cours", f.demandes.item(0, 2).text())
        self.assertNotIn("Terminée", f.demandes.item(0, 2).text())
        self.assertEqual(f.statistiques.topLevelItemCount(), 0)
        self.assertEqual(f.transactions.topLevelItemCount(), 0)
        self.assertTrue(f.statistiques.isHidden())
        self.assertIn("indisponibles", f.etat_statistiques.text())
        self.vue["etat"]["statistiques"] = {"depot": {"nombre": 3, "total_centimes": 1250}}
        f.actualiser(self.vue)
        self.assertFalse(f.statistiques.isHidden())
        self.assertEqual(f.statistiques.topLevelItem(0).child(0).text(1), "3")
        self.assertEqual(f.statistiques.topLevelItem(0).child(1).text(1), "1 250 ¢")

    def test_erreur_credit_libere_la_saisie_sans_relancer_de_demande(self):
        f = self.fenetre
        f.carte.setText("11008827F9")
        f.crediter.click()
        self.pont.erreur.emit("Journal indisponible")
        self.assertIn("Journal indisponible", f.message.text())
        self.assertTrue(f.crediter.isEnabled())
        self.assertEqual(len(self.requetes), 1)

    def test_lancement_plein_ecran_f11_quitter_et_option_fenetre(self):
        # Exécute le vrai main et la vraie fenêtre ; seule la boucle réseau est remplacée.
        self.fenetre.close()
        for arguments, plein_ecran in (([], True), (["--fenetre"], False)):
            pont = PontSimule()
            pont.thread = Mock()
            arrets = []
            pont.arret.connect(lambda: arrets.append(True))
            pont.arret.connect(pont.termine.emit)

            def observer():
                self.app.processEvents()
                fenetres = [f for f in self.app.topLevelWidgets()
                            if isinstance(f, FenetreSupervision) and f.isVisible()]
                self.assertEqual(len(fenetres), 1)
                f = fenetres[0]
                self.addCleanup(f.close)
                self.assertEqual(f.isFullScreen(), plein_ecran)
                self.app.processEvents()
                f.activateWindow()
                self.app.processEvents()
                QTest.keyClick(f, Qt.Key.Key_F11)
                self.app.processEvents()
                self.assertEqual(f.isFullScreen(), not plein_ecran)
                next(b for b in f.findChildren(QPushButton) if b.text() == "Quitter").click()
                self.app.processEvents()
                self.assertEqual(arrets, [True])
                self.assertFalse(f.isVisible())
                return 0

            with patch("commun.t13.configuration.ConfigurationMQTT.depuis_environnement",
                       return_value=ConfigurationMQTT("localhost", 1883, "esa/Equipe_1", False)), \
                 patch("pc.interface.PontPC", return_value=pont), \
                 patch("PyQt6.QtWidgets.QApplication", return_value=self.app), \
                 patch.object(self.app, "exec", side_effect=observer):
                self.assertEqual(main(["--journal", "/tmp/journal-inutilise.sqlite3"] + arguments), 0)
                pont.thread.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
