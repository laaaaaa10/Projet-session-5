"""Présentation PC : libellés, places et thème de la console ESA.

Aucune donnée métier ni décision de service n'est créée dans cette couche.
"""

import json
import unicodedata

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QRadialGradient
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget, QTreeWidget, QTreeWidgetItem


from pc.holographie import PanneauHolographique, couleur as avec_alpha


COULEURS = {"neutre": "#c0d7e9", "bleu": "#76eaff", "vert": "#65ffd3",
            "orange": "#ffe079", "rouge": "#ff9cb9"}
ETATS = {
    "EN_SERVICE": ("En service", "vert", "Les nouvelles transactions sont autorisées."),
    "MISE_HORS_SERVICE": ("Mise hors service", "orange", "La transaction confirmée se termine. Aucune nouvelle transaction."),
    "HORS_SERVICE": ("Hors service", "orange", "Les nouvelles transactions sont suspendues."),
    "ARRET_VERROUILLE": ("Arrêt verrouillé", "rouge", "Intervention et réinitialisation requises avant toute remise en service."),
    "INCONNU": ("État inconnu", "neutre", "L'état de la borne n'est pas disponible."),
}
ACTIONS = {"ARRET_IMMEDIAT": "Arrêt immédiat", "METTRE_HORS_SERVICE": "Mettre hors service",
           "REMETTRE_EN_SERVICE": "Remettre en service", "REINITIALISER": "Réinitialiser",
           "CONSULTER_SOLDE": "Consulter le solde", "AJOUTER_CREDIT": "Ajouter du crédit"}
CODES = {
    "TRANSACTION_A_TERMINER": "Fin de transaction attendue", "REARMEMENT_EN_COURS": "Réarmement en cours",
    "HORS_SERVICE": "Hors service", "EN_SERVICE": "En service", "ARRET_VERROUILLE": "Arrêt verrouillé",
    "CREDITE": "Crédit ajouté", "COMPTE_INCONNU": "Carte inconnue", "SYSTEME_NON_PRET": "Conditions de remise en service non remplies",
    "REARMEMENT_NON_SUR": "Conditions de réarmement non remplies", "REARMEMENT_REFUSE": "Réarmement refusé par la borne",
    "REARMEMENT_SANS_REPONSE": "Réarmement sans réponse", "ARRET_NON_VERROUILLE": "La borne n'est pas en arrêt verrouillé",
    "COMMANDE_EN_COURS": "Une commande est déjà en cours", "MODULE_INDISPONIBLE": "Fonction indisponible sur la borne",
    "DEMANDE_VALIDEE": "Demande acceptée", "MISE_HORS_SERVICE_DEMANDEE": "Mise hors service demandée",
    "REMISE_EN_SERVICE_DEMANDEE": "Remise en service demandée", "ARRET_DEMANDE": "Arrêt demandé",
    "INTERROMPUE_PAR_ARRET": "Procédure interrompue par un arrêt", "INTERROMPUE_PAR_DEFAUT": "Procédure interrompue par un défaut",
    "REDEMARRAGE_INTERROMPU": "Procédure interrompue par le redémarrage", "ERREUR_STOCKAGE": "Résultat incertain : erreur de stockage",
    "CONFLIT_COMMANDE": "Référence de demande incompatible", "CONFLIT_TRANSACTION": "Référence de transaction incompatible",
    "PARAMETRES_INVALIDES": "Paramètres invalides", "MESSAGE_INVALIDE": "Message invalide",
}
PLACES = {"LIBRE": ("Libre", "vert"), "RESERVEE": ("Réservée", "bleu"),
          "OCCUPEE": ("Occupée", "rouge"), "MAINTENANCE": ("Entretien", "orange"),
          "DEFAUT": ("Défaut", "orange"), "INCONNU": ("Inconnu", "neutre")}


def code(valeur):
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    return "".join(c for c in texte if not unicodedata.combining(c)).upper().replace(" ", "_")


def centimes(valeur):
    return f"{valeur:,}".replace(",", " ") + " ¢" if type(valeur) is int else "—"


def etiquette(texte="", nom="", retour=False):
    label = QLabel(texte)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setObjectName(nom)
    label.setWordWrap(retour)
    return label


def ton(widget, valeur):
    if widget.property("ton") != valeur:
        widget.setProperty("ton", valeur)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()


def resultat_lisible(resultat):
    if not resultat:
        return "En attente de réponse", "orange"
    phase, motif = resultat.get("phase"), resultat.get("code", "")
    prefixe, couleur = {"ACCEPTEE": ("En cours", "bleu"), "TERMINEE": ("Terminée", "vert"),
                        "REFUSEE": ("Refusée", "rouge"), "INCERTAINE": ("À vérifier", "orange")}.get(phase, ("À vérifier", "orange"))
    texte = CODES.get(motif, motif.replace("_", " ").capitalize())
    donnees = resultat.get("donnees") or {}
    if motif == "SOLDE":
        texte = "Solde : " + centimes(donnees.get("solde_centimes"))
    if motif == "COMPTE_INCONNU":
        couleur = "orange"
    if donnees.get("recu", {}).get("deja_traitee") or donnees.get("deja_traitee"):
        texte += " · déjà traitée"
    return f"{prefixe} · {texte}", couleur


class PlaceConsole(PanneauHolographique):
    def __init__(self, identifiant):
        super().__init__("place")
        self.identifiant = identifiant
        self.setObjectName("place")
        self.setMinimumWidth(76)
        self.setMinimumHeight(98)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 15, 6, 11)
        layout.setSpacing(4)
        self.numero = etiquette(identifiant, "numeroPlace")
        self.numero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logique = etiquette("Inconnu", "etatPlace")
        self.logique.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.presence = etiquette("IR : inconnu", "presencePlace")
        self.presence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.numero)
        layout.addStretch()
        layout.addWidget(self.logique)
        layout.addWidget(self.presence)
        self.actualiser({}, False)

    def actualiser(self, donnees, frais):
        cle = code(donnees.get("logique"))
        libelle, couleur = PLACES.get(cle, PLACES["INCONNU"])
        presence = donnees.get("presence")
        if presence is True or code(presence) == "PRESENT":
            physique = "présent"
        elif presence is False or code(presence) == "ABSENT":
            physique = "absent"
        else:
            physique = "inconnu"
        self.logique.setText(libelle)
        self.presence.setText("IR : " + physique)
        ton(self, couleur if frais else "neutre")
        self.setToolTip(f"{self.identifiant} — État logique : {libelle}. Présence physique : {physique}."
                        + (" Données périmées." if not frais else ""))


class CadranPlaces(QWidget):
    """Le cadran compte seulement les états logiques effectivement reçus."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(88, 88)
        self.valeurs = []
        self.frais = False

    def actualiser(self, valeurs, frais):
        self.valeurs, self.frais = valeurs, frais
        self.update()

    def paintEvent(self, evenement):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width() / 112, self.height() / 112)
        zone = QRectF(10, 10, 92, 92)
        halo = QRadialGradient(56, 56, 55)
        halo.setColorAt(0, QColor("#2385d4"))
        halo.setColorAt(.65, QColor("#103f86"))
        halo.setColorAt(.84, avec_alpha("#4cdeff", 95))
        halo.setColorAt(1, avec_alpha("#4cdeff", 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QRectF(0, 0, 112, 112))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(avec_alpha("#cbffff", 125), 1))
        p.drawEllipse(QRectF(3, 3, 106, 106))
        p.setPen(QPen(avec_alpha("#cbffff", 70), 1))
        p.drawEllipse(QRectF(23, 23, 66, 66))
        couleurs = {"LIBRE": "vert", "RESERVEE": "bleu", "OCCUPEE": "rouge", "MAINTENANCE": "orange", "DEFAUT": "orange"}
        for i in range(14):
            valeur = self.valeurs[i] if i < len(self.valeurs) else "INCONNU"
            couleur = COULEURS.get(couleurs.get(valeur, ""), "#7198ba") if self.frais else "#7198ba"
            pen = QPen(QColor(couleur), 7)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(zone, int((90 - i * 360 / 14) * 16), -int(19 * 16))
        p.setPen(QColor("#edf6fd"))
        p.setFont(QFont("Fredoka", 28, QFont.Weight.DemiBold))
        p.drawText(QRectF(0, 27, 112, 40), Qt.AlignmentFlag.AlignCenter, "14")
        p.setPen(QColor("#9bb7ca"))
        p.setFont(QFont("Nunito", 8, QFont.Weight.Bold))
        p.drawText(QRectF(0, 65, 112, 22), Qt.AlignmentFlag.AlignCenter, "PLACES")


class DonneesRecues(QTreeWidget):
    """Affiche tous les champs publiés, sans inventer le schéma des futurs modules."""
    def __init__(self):
        super().__init__()
        self.setHeaderLabels(["Information", "Valeur reçue"])
        self.setColumnWidth(0, 260)
        self.setAlternatingRowColors(True)
        self._signature = None

    def actualiser(self, valeur):
        signature = json.dumps(valeur, sort_keys=True, ensure_ascii=False)
        if signature == self._signature:
            return
        self._signature = signature
        self.clear()
        if valeur is None:
            return

        def ajouter(parent, nom, item, profondeur=0):
            titre = str(nom).replace("_", " ").capitalize()
            branche = QTreeWidgetItem(parent, [titre, ""])
            if profondeur < 7 and isinstance(item, (dict, list)):
                elements = item.items() if isinstance(item, dict) else enumerate(item, 1)
                for cle, enfant in elements:
                    ajouter(branche, cle, enfant, profondeur + 1)
            else:
                texte = ("Indisponible" if item is None else "Oui" if item is True else "Non" if item is False
                         else centimes(item) if str(nom).endswith("centimes") else str(item))
                branche.setText(1, texte)
        if isinstance(valeur, dict):
            for cle, item in valeur.items():
                ajouter(self, cle, item)
        elif isinstance(valeur, list):
            for i, item in enumerate(valeur, 1):
                ajouter(self, f"Transaction {i}", item)
        else:
            ajouter(self, "Valeur", valeur)
        self.expandToDepth(0)


STYLE = """
QMainWindow { background: #071b5a; }
QWidget { font-family: 'Nunito', 'DejaVu Sans'; font-size: 14px; color: #f3fbff; }
QLabel { background: transparent; }
QLabel#surTitre { color: #bae7ff; font-size: 10px; font-weight: 800; letter-spacing: 2px; }
QLabel#titrePage { font-family: 'Fredoka'; font-size: 36px; font-weight: 600; color: #f3ffff; }
QLabel#sousTitre, QLabel#secondaire { color: #c9e8fc; }
QLabel#titreBloc { font-family: 'Fredoka'; font-size: 22px; font-weight: 500; }
QLabel#etatBorne { font-family: 'Fredoka'; font-size: 31px; font-weight: 600; }
QLabel#valeur { font-family: 'Fredoka'; font-size: 34px; font-weight: 600; }
QLabel#valeurCompteur { font-family: 'Fredoka'; font-size: 25px; font-weight: 600; }
QLabel#petit { font-size: 11px; color: #c0dcf2; }
QFrame#rail QLabel { color: #27517d; }
QFrame#rail QLabel#surTitre { color: #31557a; }
QFrame#rail QLabel#petit { font-size: 9px; font-weight: 800; letter-spacing: 1px; }
QLabel#numeroPlace { font-family: 'Fredoka'; font-size: 24px; font-weight: 500; }
QLabel#etatPlace { font-weight: 800; font-size: 13px; }
QLabel#presencePlace { font-size: 10px; color: #d1e4f5; }
QLabel#bandeau { border: 1px solid #64e4cd; border-radius: 19px; padding: 9px 17px; font-weight: 800; background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #206f91,stop:1 #123b6d); color: #91ffdb; }
QLabel#bandeau[ton=orange] { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #66591e,stop:1 #3e3661); color: #ffe991; border-color: #e7c263; }
QLabel#bandeau[ton=rouge] { background: #62385a; color: #ffbed4; border-color: #f47eae; }
QLabel#simulation { border: 1px solid #a59b83; border-radius: 15px; padding: 7px 16px; color: #ffe3a2; background: rgba(50,38,55,160); font-size: 12px; }
QLabel[ton=vert] { color: #7cffd7; }
QLabel[ton=rouge] { color: #ff9cbd; }
QLabel[ton=orange] { color: #ffe181; }
QLabel[ton=bleu] { color: #8befff; }
QLabel[ton=neutre] { color: #d5e8f7; }
QPushButton { border: 1px solid #90dfff; border-bottom: 2px solid #447db7; border-radius: 21px; padding: 9px 16px; background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #5faed7,stop:0.44 #286ca8,stop:1 #19437f); color: #f4fcff; font-weight: 800; min-height: 21px; }
QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #9be9ff,stop:0.5 #278fe0,stop:1 #1d58b6); border-color: #d6ffff; }
QPushButton:pressed { background: #17447a; border-bottom-width: 1px; }
QPushButton:focus { border: 2px solid #ffe576; }
QPushButton:disabled { color: #a8b9ca; background: #304c6c; border-color: #61748a; }
QPushButton#primaire { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #9ef5ff,stop:0.35 #149de8,stop:1 #2558d7); border-color: #acf6ff; }
QPushButton#primaire:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #d2ffff,stop:0.35 #36bbf9,stop:1 #3868ec); }
QPushButton#primaire:disabled { background: #304c6c; border-color: #61748a; }
QPushButton#navigation { text-align: left; background: transparent; color: #244d7b; border: 1px solid transparent; border-radius: 21px; padding: 5px 8px; font-size: 13px; min-height: 34px; }
QPushButton#navigation:hover { background: #e0f6ff; border-color: #ffffff; }
QPushButton#navigation:checked { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #63d7ff,stop:0.46 #1688df,stop:1 #1753bd); color: white; border-color: #e8ffff; }
QPushButton#commandeRail { color: #164a77; background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f8ffff,stop:0.5 #ceeaff,stop:1 #9ac9ea); border-color: #f1ffff; border-bottom-color: #86a9ce; font-size: 12px; padding: 8px 5px; border-radius: 19px; }
QPushButton#commandeRail:hover { background: #e7fbff; border-color: #358dde; }
QPushButton#commandeRail:disabled { color: #72869a; background: #b1c8da; border-color: #cadce8; }
QPushButton#arret { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffb1be,stop:0.32 #f34366,stop:0.75 #d52650,stop:1 #a51741); border: 2px solid #ffe4ed; border-bottom-color: #9b3258; border-radius: 34px; color: white; font-family: 'Fredoka'; font-size: 20px; font-weight: 600; min-height: 53px; }
QPushButton#arret:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffd3df,stop:0.4 #ff4c79,stop:1 #e12759); }
QPushButton#arret:disabled { background: #8a7189; border-color: #c0a8b9; color: #ded3e0; }
QPushButton#outil { color: #265680; background: rgba(229,247,255,120); border: 1px solid #ddf5ff; border-radius: 15px; font-size: 11px; padding: 5px; min-height: 20px; }
QLineEdit, QSpinBox { background: rgba(4,29,75,185); color: #f3fcff; border: 1px solid #73b9e3; border-radius: 20px; padding: 11px 15px; selection-background-color: #2e89da; }
QLineEdit:focus, QSpinBox:focus { border: 2px solid #abf9ff; }
QSpinBox::up-button, QSpinBox::down-button { width: 25px; }
QTableWidget, QTreeWidget, QPlainTextEdit { background: rgba(9,36,80,185); alternate-background-color: rgba(31,76,126,160); color: #f1faff; border: 1px solid #6aa7d6; border-radius: 20px; gridline-color: #32618c; selection-background-color: #227ccc; selection-color: white; }
QHeaderView { background: transparent; }
QHeaderView::section { background: #22639e; color: #dcf6ff; padding: 12px; border: none; border-bottom: 1px solid #75c8f0; font-size: 12px; font-weight: 800; }
QTableWidget::item, QTreeWidget::item { padding: 7px; }
QTableWidget::item:selected, QTreeWidget::item:selected { background: #257bbd; color: white; }
QTabWidget::pane { border: none; padding-top: 12px; }
QTabBar::tab { background: #265b97; color: #c6e9ff; padding: 12px 24px; margin-right: 8px; border: 1px solid #6caedb; border-radius: 21px; }
QTabBar::tab:selected { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #68d4ef,stop:0.4 #278cdb,stop:1 #244db3); color: white; border-color: #a3efff; }
QScrollArea { background: transparent; border: none; }
QWidget#page { background: transparent; }
QScrollBar:vertical { background: rgba(15,44,89,110); width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #74b5d9; min-height: 25px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { color: #103a6b; background: #e5faff; border: 1px solid #70bde7; padding: 7px; }
"""
