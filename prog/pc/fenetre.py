"""Console opérateur ESA. Le Pi reste l'autorité pour toutes les commandes."""

import json
import re

from PyQt6.QtCore import Qt, QDateTime, QTimer, pyqtSlot
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLineEdit, QMainWindow, QPlainTextEdit, QPushButton,
    QScrollArea, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from pc.visuels import (ACTIONS, COULEURS, ETATS, PLACES, STYLE, CadranPlaces,
                       DonneesRecues, PlaceConsole, centimes, code, etiquette,
                       resultat_lisible, ton)


def panneau(titre=None, nom="panneau"):
    cadre = QFrame()
    cadre.setObjectName(nom)
    layout = QVBoxLayout(cadre)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(14)
    if titre:
        layout.addWidget(etiquette(titre, "titreBloc"))
    return cadre, layout


def tableau(entetes):
    table = QTableWidget(0, len(entetes))
    table.setHorizontalHeaderLabels(entetes)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(46)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def cellule(table, ligne, colonne, texte):
    item = table.item(ligne, colonne)
    if item is None:
        item = QTableWidgetItem(texte)
        table.setItem(ligne, colonne, item)
    elif item.text() != texte:
        item.setText(texte)
    return item


class FenetreSupervision(QMainWindow):
    TITRES = [("VUE D’ENSEMBLE", "Le stationnement, en un regard."),
              ("COMPTES RFID", "Consulter un solde et ajouter du crédit."),
              ("ACTIVITÉ", "Suivre les demandes et les transactions de la borne."),
              ("STATISTIQUES", "Les indicateurs transmis par la borne."),
              ("DIAGNOSTIC", "Connexion, disponibilité et données techniques.")]

    def __init__(self, pont):
        super().__init__()
        self.pont = pont
        self._fermeture = self._termine = self._donnees_fraiches = False
        self._selection = None
        self._vue = {"statut": "DECONNECTE", "etat": None, "demandes": []}
        self._soldes = {}
        self._credit_soumis = False
        self._credits_avant = set()
        self._signature = self._signature_comptes = self._revision = None
        self.setWindowTitle("ESA — Centre de supervision")
        self.resize(1440, 900)
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(STYLE)
        contenu = QWidget()
        contenu.setObjectName("console")
        self.setCentralWidget(contenu)
        racine = QHBoxLayout(contenu)
        racine.setContentsMargins(14, 14, 22, 14)
        racine.setSpacing(24)
        self.commandes_service = {}
        self.navigation = []
        self._construire_rail(racine)
        principal = QVBoxLayout()
        principal.setSpacing(12)
        racine.addLayout(principal, 1)
        entete = QHBoxLayout()
        titres = QVBoxLayout()
        titres.setSpacing(5)
        titres.addWidget(etiquette("ESA  /  CENTRE DE SUPERVISION", "surTitre"))
        self.titre_page = etiquette("", "titrePage")
        self.sous_titre = etiquette("", "sousTitre")
        titres.addWidget(self.titre_page)
        titres.addWidget(self.sous_titre)
        entete.addLayout(titres, 1)
        self.equipe = etiquette("BORNE\n—", "surTitre")
        self.equipe.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        config = getattr(getattr(pont, "travailleur", None), "config", None)
        if config is not None:
            self.equipe.setText(config.prefixe.replace("esa/", "").replace("_", " ").upper())
        entete.addWidget(self.equipe)
        principal.addLayout(entete)
        self.connexion = etiquette("Connexion en cours — données indisponibles", "bandeau", True)
        ton(self.connexion, "orange")
        principal.addWidget(self.connexion)
        self.simulation = etiquette("MODE SIMULATION  ·  Séquences et sécurité simulées — aucun moteur commandé", "simulation", True)
        self.simulation.hide()
        principal.addWidget(self.simulation)
        self.pages = QStackedWidget()
        principal.addWidget(self.pages, 1)
        self._construire_vue_ensemble()
        self._construire_comptes()
        self._construire_activite()
        self._construire_statistiques()
        self._construire_diagnostic(config)
        self.message = etiquette("", "petit", True)
        self.message.hide()
        principal.addWidget(self.message)
        pied = QHBoxLayout()
        pied.addWidget(etiquette("PC  ↔  BROKER MQTT  ↔  PI", "surTitre"))
        pied.addStretch()
        self.actualisation = etiquette("En attente du premier état", "petit")
        pied.addWidget(self.actualisation)
        principal.addLayout(pied)
        self.afficher_page(0)
        self._raccourcis = []
        for touche, fonction in (("F11", self.basculer_plein_ecran), ("Ctrl+Q", self.close)):
            raccourci = QShortcut(QKeySequence(touche), self)
            raccourci.activated.connect(fonction)
            self._raccourcis.append(raccourci)
        pont.vue.connect(self.actualiser)
        pont.erreur.connect(self._erreur)
        pont.termine.connect(self._arrete)
        self._actualiser_commandes()

    def _construire_rail(self, racine):
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(224)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(16, 20, 16, 14)
        layout.setSpacing(8)
        marque = etiquette("ESA", "marque")
        marque.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(marque)
        signature = etiquette("STATIONNEMENT AUTOMATISÉ", "petit")
        signature.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(signature)
        layout.addSpacing(10)
        self._groupe_navigation = QButtonGroup(self)
        for i, libelle in enumerate(("Vue d’ensemble", "Comptes RFID", "Activité", "Statistiques", "Diagnostic")):
            bouton = QPushButton(f"0{i + 1}   {libelle}")
            bouton.setObjectName("navigation")
            bouton.setCheckable(True)
            bouton.clicked.connect(lambda checked=False, index=i: self.afficher_page(index))
            self._groupe_navigation.addButton(bouton, i)
            self.navigation.append(bouton)
            layout.addWidget(bouton)
        layout.addStretch(1)
        layout.addWidget(etiquette("COMMANDES BORNE", "surTitre"))
        for action in ("REMETTRE_EN_SERVICE", "METTRE_HORS_SERVICE", "REINITIALISER", "ARRET_IMMEDIAT"):
            texte = "ARRÊT\nIMMÉDIAT" if action == "ARRET_IMMEDIAT" else ACTIONS[action]
            bouton = QPushButton(texte)
            bouton.setObjectName("arret" if action == "ARRET_IMMEDIAT" else "commandeRail")
            bouton.setEnabled(False)
            bouton.setToolTip({
                "ARRET_IMMEDIAT": "Demander l'arrêt logiciel et verrouiller la borne.",
                "METTRE_HORS_SERVICE": "Suspendre les nouvelles transactions et laisser finir celle déjà confirmée.",
                "REMETTRE_EN_SERVICE": "Demander la remise en service ; la borne vérifie ses conditions.",
                "REINITIALISER": "Après intervention, demander le réarmement. La réussite ramène hors service.",
            }[action])
            bouton.clicked.connect(lambda checked=False, action=action: self._demander_service(action))
            self.commandes_service[action] = bouton
            layout.addWidget(bouton)
        outils = QHBoxLayout()
        fenetre = QPushButton("F11 · Écran")
        fenetre.setObjectName("outil")
        fenetre.setToolTip("Basculer entre plein écran et fenêtre (F11)")
        fenetre.clicked.connect(self.basculer_plein_ecran)
        quitter = QPushButton("Quitter")
        quitter.setObjectName("outil")
        quitter.setToolTip("Fermer la supervision PC (Ctrl+Q)")
        quitter.clicked.connect(self.close)
        outils.addWidget(fenetre)
        outils.addWidget(quitter)
        layout.addLayout(outils)
        racine.addWidget(rail)

    def _page(self):
        page = QWidget()
        page.setObjectName("page")
        disposition = QVBoxLayout(page)
        disposition.setContentsMargins(2, 2, 8, 2)
        disposition.setSpacing(16)
        defilement = QScrollArea()
        defilement.setWidgetResizable(True)
        defilement.setWidget(page)
        self.pages.addWidget(defilement)
        return disposition

    def _construire_vue_ensemble(self):
        page = self._page()
        synthese = QHBoxLayout()
        synthese.setSpacing(16)
        hero, contenu = panneau(nom="hero")
        contenu.setContentsMargins(18, 14, 18, 14)
        ligne = QHBoxLayout()
        texte = QVBoxLayout()
        self.origine_etat = etiquette("ÉTAT DE LA BORNE", "surTitre", True)
        self.service = etiquette("État inconnu", "etatBorne", True)
        self.explication_service = etiquette("En attente de données.", "secondaire", True)
        texte.addWidget(self.origine_etat)
        texte.addWidget(self.service)
        texte.addWidget(self.explication_service)
        ligne.addLayout(texte, 1)
        self.cadran = CadranPlaces()
        ligne.addWidget(self.cadran)
        contenu.addLayout(ligne)
        synthese.addWidget(hero, 3)
        compteurs = QGridLayout()
        compteurs.setSpacing(10)
        self.compteurs = {}
        for index, (cle, titre, couleur) in enumerate((("LIBRE", "LIBRES CONNUES", "vert"), ("OCCUPEE", "OCCUPÉES CONNUES", "rouge"),
                                    ("RESERVEE", "RÉSERVÉES CONNUES", "bleu"), ("INCONNU", "NON RENSEIGNÉES", "neutre"))):
            cadre, interieur = panneau(nom="compteur")
            interieur.setContentsMargins(14, 7, 14, 7)
            interieur.setSpacing(1)
            valeur = etiquette("—", "valeurCompteur")
            ton(valeur, couleur)
            interieur.addWidget(valeur)
            interieur.addWidget(etiquette(titre, "petit"))
            self.compteurs[cle] = valeur
            compteurs.addWidget(cadre, index // 2, index % 2)
        synthese.addLayout(compteurs, 2)
        page.addLayout(synthese)
        places, interieur = panneau("PLAN DU STATIONNEMENT")
        interieur.setContentsMargins(16, 14, 16, 14)
        interieur.setSpacing(8)
        interieur.addWidget(etiquette("14 emplacements · 2 niveaux    /    Présence physique IR indiquée sous chaque état", "secondaire", True))
        self.places = {}
        for etage in (1, 2):
            interieur.addWidget(etiquette(f"NIVEAU 0{etage}", "surTitre"))
            rang = QHBoxLayout()
            rang.setSpacing(8)
            for numero in range(1, 8):
                identifiant = f"E{etage}.{numero}"
                place = PlaceConsole(identifiant)
                self.places[identifiant] = place
                rang.addWidget(place, 1)
            interieur.addLayout(rang)
        page.addWidget(places)
        anomalies, interieur = panneau("INFORMATIONS DE LA BORNE")
        self.anomalies = etiquette("Données indisponibles.", "secondaire", True)
        interieur.addWidget(self.anomalies)
        self.derniere_demande = etiquette("Aucune demande enregistrée.", "petit", True)
        interieur.addWidget(self.derniere_demande)
        page.addWidget(anomalies)
        page.addStretch()

    def _construire_comptes(self):
        page = self._page()
        ligne = QHBoxLayout()
        ligne.setSpacing(18)
        liste, interieur = panneau("CARTES ENREGISTRÉES")
        self.recherche_comptes = QLineEdit()
        self.recherche_comptes.setPlaceholderText("Rechercher un identifiant de carte…")
        self.recherche_comptes.setAccessibleName("Rechercher une carte")
        self.recherche_comptes.textChanged.connect(self._afficher_comptes)
        interieur.addWidget(self.recherche_comptes)
        self.comptes = tableau(["Carte RFID", "Solde"])
        self.comptes.setMinimumHeight(260)
        self.comptes.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.comptes.itemSelectionChanged.connect(self._choisir_carte)
        interieur.addWidget(self.comptes, 1)
        self.etat_comptes = etiquette("Comptes indisponibles.", "secondaire", True)
        interieur.addWidget(self.etat_comptes)
        ligne.addWidget(liste, 3)
        recharge, interieur = panneau("CONSULTATION & CRÉDIT")
        recharge.setMinimumWidth(300)
        interieur.addWidget(etiquette("Sélectionne une carte ou saisis son identifiant complet.", "secondaire", True))
        interieur.addWidget(etiquette("IDENTIFIANT DE CARTE", "surTitre"))
        self.carte = QLineEdit()
        self.carte.setMaxLength(64)  # Ne pas tronquer un identifiant trop long en carte valide.
        self.carte.setPlaceholderText("10 caractères · ex. 11008827F9")
        self.carte.setAccessibleName("Identifiant de carte RFID")
        self.carte.textChanged.connect(self._carte_modifiee)
        interieur.addWidget(self.carte)
        interieur.addWidget(etiquette("SOLDE COURANT REÇU", "surTitre"))
        self.solde_selectionne = etiquette("—", "valeur")
        interieur.addWidget(self.solde_selectionne)
        self.consulter = QPushButton("Consulter le solde")
        self.consulter.clicked.connect(lambda: self._demander("CONSULTER_SOLDE"))
        interieur.addWidget(self.consulter)
        interieur.addSpacing(14)
        interieur.addWidget(etiquette("CRÉDIT À AJOUTER", "surTitre"))
        self.montant = QSpinBox()
        self.montant.setRange(1, 2_147_483_647)
        self.montant.setValue(500)
        self.montant.setSuffix(" ¢")
        self.montant.setAccessibleName("Montant du crédit en centimes")
        interieur.addWidget(self.montant)
        presets = QHBoxLayout()
        for valeur in (200, 500, 1000):
            bouton = QPushButton(centimes(valeur))
            bouton.clicked.connect(lambda checked=False, valeur=valeur: self.montant.setValue(valeur))
            presets.addWidget(bouton)
        interieur.addLayout(presets)
        self.crediter = QPushButton("Ajouter ce crédit")
        self.crediter.setObjectName("primaire")
        self.crediter.clicked.connect(lambda: self._demander("AJOUTER_CREDIT"))
        interieur.addWidget(self.crediter)
        self.aide_compte = etiquette("Choisis une carte pour commencer.", "secondaire", True)
        interieur.addWidget(self.aide_compte)
        self.resultat_compte = etiquette("", "secondaire", True)
        interieur.addWidget(self.resultat_compte)
        interieur.addStretch()
        ligne.addWidget(recharge, 2)
        page.addLayout(ligne, 1)

    def _construire_activite(self):
        page = self._page()
        self.onglets_activite = QTabWidget()
        demandes = QWidget()
        disposition = QVBoxLayout(demandes)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(14)
        disposition.addWidget(etiquette("Une demande en cours attend encore son résultat final.", "secondaire", True))
        self.demandes = tableau(["Référence", "Demande", "Résultat"])
        self.demandes.setColumnHidden(0, True)
        self.demandes.setColumnWidth(1, 220)
        self.demandes.setMinimumHeight(310)
        self.demandes.itemSelectionChanged.connect(self._selectionner)
        disposition.addWidget(self.demandes, 1)
        self.details_demande = etiquette("Sélectionne une demande pour consulter sa référence et ses détails.", "secondaire", True)
        self.details_demande.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        disposition.addWidget(self.details_demande)
        self.reprendre = QPushButton("Renvoyer cette demande")
        self.reprendre.setEnabled(False)
        self.reprendre.setToolTip("Réutilise exactement la même demande et le même identifiant, sans créer une nouvelle opération.")
        self.reprendre.clicked.connect(self._reprendre)
        disposition.addWidget(self.reprendre, alignment=Qt.AlignmentFlag.AlignLeft)
        self.onglets_activite.addTab(demandes, "Demandes PC")
        transactions = QWidget()
        disposition = QVBoxLayout(transactions)
        self.etat_transactions = etiquette("Les transactions ne sont pas encore disponibles.", "secondaire", True)
        disposition.addWidget(self.etat_transactions)
        self.transactions = DonneesRecues()
        self.transactions.setMinimumHeight(310)
        self.transactions.hide()
        disposition.addWidget(self.transactions, 1)
        self.attente_transactions = self._attente("Aucune transaction reçue", "Les opérations publiées par la borne apparaîtront ici.")
        disposition.addWidget(self.attente_transactions, 1)
        self.onglets_activite.addTab(transactions, "Transactions de la borne")
        page.addWidget(self.onglets_activite, 1)

    def _construire_statistiques(self):
        page = self._page()
        cadre, interieur = panneau("INDICATEURS D’EXPLOITATION")
        self.etat_statistiques = etiquette("Les statistiques ne sont pas encore disponibles.", "secondaire", True)
        interieur.addWidget(self.etat_statistiques)
        self.statistiques = DonneesRecues()
        self.statistiques.setMinimumHeight(360)
        self.statistiques.hide()
        interieur.addWidget(self.statistiques, 1)
        self.attente_statistiques = self._attente("En attente des statistiques", "Les indicateurs seront affichés dès leur réception.")
        interieur.addWidget(self.attente_statistiques, 1)
        page.addWidget(cadre, 1)

    @staticmethod
    def _attente(titre, description):
        cadre = QWidget()
        cadre.setMinimumHeight(280)
        disposition = QVBoxLayout(cadre)
        disposition.setSpacing(12)
        disposition.addStretch()
        for texte, nom in (("···", "etatBorne"), (titre, "titreBloc"), (description, "secondaire")):
            label = etiquette(texte, nom, True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            disposition.addWidget(label)
        disposition.addStretch()
        return cadre

    def _construire_diagnostic(self, config):
        page = self._page()
        cadre, interieur = panneau("LIAISON & DISPONIBILITÉ")
        self.reseau = etiquette("Configuration du banc de test", "secondaire", True)
        if config is not None:
            self.reseau.setText(f"Broker : {config.hote}:{config.port}\nPréfixe : {config.prefixe}\nTLS : {'activé' if config.tls else 'désactivé'}")
        interieur.addWidget(self.reseau)
        self.disponibilite = etiquette("En attente des disponibilités.", "secondaire", True)
        interieur.addWidget(self.disponibilite)
        page.addWidget(cadre)
        cadre, interieur = panneau("ÉTAT TECHNIQUE REÇU")
        interieur.addWidget(etiquette("Lecture seule · valeurs publiées par le Raspberry Pi", "secondaire"))
        self.informations = QPlainTextEdit()
        self.informations.setReadOnly(True)
        self.informations.setMinimumHeight(300)
        interieur.addWidget(self.informations, 1)
        page.addWidget(cadre, 1)

    def afficher_page(self, index):
        self.pages.setCurrentIndex(index)
        self.navigation[index].setChecked(True)
        self.titre_page.setText(self.TITRES[index][0])
        self.sous_titre.setText(self.TITRES[index][1])

    def basculer_plein_ecran(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def _carte_modifiee(self):
        identifiant = self.carte.text().strip().upper()
        self.solde_selectionne.setText(centimes(self._soldes.get(identifiant)))
        self._actualiser_commandes()
        self._resultat_compte()

    def _choisir_carte(self):
        lignes = self.comptes.selectionModel().selectedRows(0)
        if len(lignes) == 1:
            self.carte.setText(lignes[0].data())

    def _afficher_comptes(self):
        filtre = self.recherche_comptes.text().strip().upper()
        soldes = [(carte, solde) for carte, solde in sorted(self._soldes.items()) if filtre in carte]
        signature = (tuple(soldes), filtre)
        if signature == self._signature_comptes:
            return
        self._signature_comptes = signature
        selection = self.comptes.selectionModel().selectedRows(0)
        identifiant = selection[0].data() if selection else None
        self.comptes.blockSignals(True)
        self.comptes.setRowCount(len(soldes))
        self.comptes.clearSelection()
        for ligne, (carte, solde) in enumerate(soldes):
            cellule(self.comptes, ligne, 0, carte)
            cellule(self.comptes, ligne, 1, centimes(solde))
            if carte == identifiant:
                self.comptes.selectRow(ligne)
        self.comptes.blockSignals(False)

    def _actualiser_commandes(self):
        etat = self._vue.get("etat") or {}
        actif = self._donnees_fraiches and not self._fermeture and not self._termine
        disponibilite = etat.get("disponibilite") or {}
        for bouton in self.commandes_service.values():
            bouton.setEnabled(actif and disponibilite.get("service", False))
        if not hasattr(self, "consulter"):
            return
        valide = re.fullmatch(r"[0-9A-Fa-f]{10}", self.carte.text().strip()) is not None
        disponible = actif and disponibilite.get("T02", False)
        attente = self._credit_soumis or any(not d["termine"] and d["demande"]["commande"] == "AJOUTER_CREDIT"
                                           for d in self._vue["demandes"])
        self.consulter.setEnabled(disponible and valide)
        self.crediter.setEnabled(disponible and valide and not attente)
        self.aide_compte.setText("Données à jour requises pour envoyer une demande." if not actif else
                               "La gestion des comptes est indisponible sur la borne." if not disponible else
                               "Crédit en attente. Consulte Activité pour retrouver la demande." if attente else
                               "Identifiant requis : 10 caractères hexadécimaux." if not valide else
                               "Le crédit sera confirmé par la borne.")
        if hasattr(self, "reprendre"):
            self._actualiser_reprise()

    def _demander(self, action):
        bouton = self.crediter if action == "AJOUTER_CREDIT" else self.consulter
        if not bouton.isEnabled():
            return
        params = {"id_uart": self.carte.text().strip().upper()}
        if action == "AJOUTER_CREDIT":
            params["montant_centimes"] = self.montant.value()
            self._credits_avant = {d["demande"]["id_commande"] for d in self._vue["demandes"]}
            self._credit_soumis = True
            self.crediter.setEnabled(False)
        self._message("Demande envoyée · " + ACTIONS[action], "bleu")
        self.pont.requete.emit(action, params)

    def _demander_service(self, action):
        if self.commandes_service[action].isEnabled():
            self._message("Demande envoyée · " + ACTIONS[action] + ". Le résultat apparaît dans Activité.", "bleu")
            self.pont.requete.emit(action, {})

    def _message(self, texte, couleur):
        self.message.setText(texte)
        ton(self.message, couleur)
        self.message.setVisible(bool(texte))

    def _erreur(self, texte):
        self._credit_soumis = False
        self._actualiser_commandes()
        self._message(texte, "rouge")

    def _selectionner(self):
        lignes = self.demandes.selectionModel().selectedRows(0)
        self._selection = lignes[0].data() if len(lignes) == 1 else None
        self._actualiser_reprise()
        self._details_selection()

    def _details_selection(self):
        entree = next((d for d in self._vue["demandes"] if d["demande"]["id_commande"] == self._selection), None)
        if entree is None:
            self.details_demande.setText("Sélectionne une demande pour consulter sa référence et ses détails.")
            return
        demande, resultat = entree["demande"], entree["reponse"]
        details = ["Référence : " + demande["id_commande"]]
        params = demande.get("parametres") or {}
        if params.get("id_uart"):
            details.append("Carte : " + params["id_uart"])
        if "montant_centimes" in params:
            details.append("Crédit demandé : " + centimes(params["montant_centimes"]))
        if resultat:
            details.append("Code : " + resultat["code"])
        self.details_demande.setText("\n".join(details))

    def _actualiser_reprise(self):
        self.reprendre.setEnabled(self._donnees_fraiches and self._selection is not None
                                  and not self._fermeture and not self._termine)

    def _reprendre(self):
        if self.reprendre.isEnabled() and self._selection:
            self.pont.requete.emit("REPRENDRE_DEMANDE", {"id_commande": self._selection})

    def _resultat_compte(self):
        carte = self.carte.text().strip().upper()
        entree = next((d for d in self._vue["demandes"] if d["demande"].get("parametres", {}).get("id_uart") == carte), None)
        texte, couleur = resultat_lisible(entree["reponse"]) if entree else ("", "neutre")
        self.resultat_compte.setText(texte)
        ton(self.resultat_compte, couleur)

    @pyqtSlot(object)
    def actualiser(self, vue):
        signature = json.dumps(vue, sort_keys=True, ensure_ascii=False)
        if signature == self._signature:
            return
        self._signature = signature
        self._vue = vue
        frais = vue["statut"] == "A_JOUR" and not self._termine and not self._fermeture
        self._donnees_fraiches = frais
        if self._termine:
            connexion, couleur = "Application arrêtée — données périmées", "rouge"
        else:
            connexion, couleur = {
                "A_JOUR": ("●  PC ↔ broker MQTT ↔ Pi — données à jour", "vert"),
                "PERIMEES": ("●  Broker connecté — données périmées, attente du Pi", "orange"),
                "DECONNECTE": ("●  Déconnecté du broker — données périmées", "rouge"),
            }.get(vue["statut"], ("Connexion en cours — données indisponibles", "orange"))
        self.connexion.setText(connexion)
        ton(self.connexion, couleur)
        etat = vue.get("etat") or {}
        self.simulation.setVisible(etat.get("service_simule") is True)
        nom, couleur, explication = ETATS.get(etat.get("etat_service"), ETATS["INCONNU"])
        self.service.setText(nom)
        ton(self.service, couleur if frais else "neutre")
        self.origine_etat.setText("ÉTAT DE LA BORNE" if frais else "DERNIER ÉTAT CONNU · DONNÉES PÉRIMÉES")
        self.explication_service.setText(explication if frais else "La connexion doit être rétablie pour confirmer l'état actuel.")
        revision = (etat.get("session"), etat.get("revision"))
        if etat and frais and revision != self._revision:
            self._revision = revision
            self.actualisation.setText("Dernier état reçu · " + QDateTime.currentDateTime().toString("HH:mm:ss"))
        places = {p["id"]: p for p in etat.get("places", []) if p.get("id") in self.places}
        valeurs = []
        for identifiant, widget in self.places.items():
            valeur = places.get(identifiant, {})
            widget.actualiser(valeur, frais)
            logique = code(valeur.get("logique"))
            valeurs.append(logique if logique in PLACES else "INCONNU")
        self.cadran.actualiser(valeurs, frais)
        inconnus = valeurs.count("INCONNU")
        for cle, label in self.compteurs.items():
            label.setText(str(inconnus) if cle == "INCONNU" else ("—" if inconnus == 14 else str(valeurs.count(cle))))
        self._soldes = etat.get("soldes") or {}
        self._afficher_comptes()
        self.solde_selectionne.setText(centimes(self._soldes.get(self.carte.text().strip().upper())))
        self.etat_comptes.setText("Comptes indisponibles." if etat.get("soldes") is None else
                                  f"{len(self._soldes)} carte(s) reçue(s) · sélectionne une ligne." + (" Données périmées." if not frais else ""))
        if self._credit_soumis and any(d["demande"]["commande"] == "AJOUTER_CREDIT" and
                                      d["demande"]["id_commande"] not in self._credits_avant for d in vue["demandes"]):
            self._credit_soumis = False
        self._actualiser_commandes()
        anomalies = []
        for anomalie in etat.get("anomalies", []):
            if isinstance(anomalie, dict):
                identifiant = anomalie.get("code")
                if identifiant == "SIMULATION_SERVICE":
                    continue
                texte = {"MODULES_NON_RACCORDES": "Certaines données de la borne ne sont pas encore disponibles.",
                         "ARRET_VERROUILLE": "Arrêt verrouillé : intervention puis réinitialisation requises.",
                         "DEFAUT_ACTIF": "Un défaut est actif sur la borne."}.get(identifiant, anomalie.get("message", identifiant or "Anomalie"))
            else:
                texte = str(anomalie)
            anomalies.append("• " + str(texte))
        self.anomalies.setText("\n".join(anomalies) if anomalies else
                              ("Aucune anomalie signalée." if frais and "anomalies" in etat else "Anomalies non disponibles ou périmées."))
        for cle, arbre, description, attente in (("transactions", self.transactions, self.etat_transactions, self.attente_transactions),
                                                 ("statistiques", self.statistiques, self.etat_statistiques, self.attente_statistiques)):
            valeur = etat.get(cle)
            arbre.actualiser(valeur)
            vide = valeur is None or valeur in ([], {})
            arbre.setVisible(not vide)
            attente.setVisible(vide)
            description.setText("Données indisponibles : la borne ne transmet pas encore ces informations." if valeur is None else
                                "Aucun enregistrement transmis." if valeur in ([], {}) else
                                "Informations transmises par la borne." if frais else "Dernières informations reçues · données périmées.")
        self.disponibilite.setText("\n".join(f"{cle} : {'disponible' if dispo else 'indisponible'}"
                                            for cle, dispo in sorted(etat.get("disponibilite", {}).items())))
        informations = json.dumps(etat, ensure_ascii=False, indent=2, sort_keys=True)
        if self.informations.toPlainText() != informations:
            defilement = self.informations.verticalScrollBar().value()
            self.informations.setPlainText(informations)
            self.informations.verticalScrollBar().setValue(defilement)
        self.demandes.blockSignals(True)
        self.demandes.setRowCount(len(vue["demandes"]))
        ligne_selection = None
        for ligne, entree in enumerate(vue["demandes"]):
            demande, resultat = entree["demande"], entree["reponse"]
            texte, couleur = resultat_lisible(resultat)
            cellule(self.demandes, ligne, 0, demande["id_commande"])
            cellule(self.demandes, ligne, 1, ACTIONS.get(demande["commande"], demande["commande"]))
            item = cellule(self.demandes, ligne, 2, texte)
            item.setForeground(QColor(COULEURS[couleur]))
            if demande["id_commande"] == self._selection:
                ligne_selection = ligne
        if ligne_selection is not None:
            selection = self.demandes.selectionModel().selectedRows()
            if [i.row() for i in selection] != [ligne_selection]:
                self.demandes.selectRow(ligne_selection)
        else:
            self.demandes.clearSelection()
            self._selection = None
        self.demandes.blockSignals(False)
        self._actualiser_reprise()
        self._details_selection()
        self._resultat_compte()
        if vue["demandes"]:
            entree = vue["demandes"][0]
            texte, _ = resultat_lisible(entree["reponse"])
            self.derniere_demande.setText("Dernière demande · " + ACTIONS.get(entree["demande"]["commande"], entree["demande"]["commande"]) + " — " + texte)
        else:
            self.derniere_demande.setText("Aucune demande enregistrée.")

    def closeEvent(self, evenement):
        if self._termine:
            evenement.accept()
            return
        evenement.ignore()
        if not self._fermeture:
            self._fermeture = True
            self.centralWidget().setEnabled(False)
            self._message("Fermeture du client MQTT…", "neutre")
            self.pont.arret.emit()

    def _arrete(self):
        self._termine = True
        self._donnees_fraiches = False
        self._signature = None
        if self._fermeture:
            QTimer.singleShot(0, self.close)
        else:
            self.actualiser(self._vue)
