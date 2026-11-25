"""Présentation PC : libellés, places et thème de la console ESA.

Aucune donnée métier ni décision de service n'est créée dans cette couche.
"""

import json
import unicodedata

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QFont
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget, QTreeWidget, QTreeWidgetItem


COULEURS = {"neutre": "#9bb7ca", "bleu": "#6bc9ff", "vert": "#66dec0",
            "orange": "#ffc565", "rouge": "#ff8d91"}
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


class PlaceConsole(QFrame):
    def __init__(self, identifiant):
        super().__init__()
        self.identifiant = identifiant
        self.setObjectName("place")
        self.setMinimumWidth(76)
        self.setMinimumHeight(94)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 12, 9, 12)
        layout.setSpacing(8)
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
        zone = QRectF(9, 9, 94, 94)
        couleurs = {"LIBRE": "vert", "RESERVEE": "bleu", "OCCUPEE": "rouge", "MAINTENANCE": "orange", "DEFAUT": "orange"}
        for i in range(14):
            valeur = self.valeurs[i] if i < len(self.valeurs) else "INCONNU"
            couleur = COULEURS.get(couleurs.get(valeur, ""), "#38556c") if self.frais else "#38556c"
            pen = QPen(QColor(couleur), 7)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(zone, int((90 - i * 360 / 14) * 16), -int(19 * 16))
        p.setPen(QColor("#edf6fd"))
        p.setFont(QFont("DejaVu Sans", 24, QFont.Weight.Bold))
        p.drawText(QRectF(0, 27, 112, 40), Qt.AlignmentFlag.AlignCenter, "14")
        p.setPen(QColor("#9bb7ca"))
        p.setFont(QFont("DejaVu Sans", 8, QFont.Weight.Bold))
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
QMainWindow, QWidget#console { background: #091e30; color: #edf6fd; }
QWidget { font-family: 'DejaVu Sans'; font-size: 13px; color: #edf6fd; }
QLabel { background: transparent; }
QLabel#surTitre { color: #9bb7ca; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#titrePage { font-size: 29px; font-weight: 800; letter-spacing: 1px; }
QLabel#sousTitre, QLabel#secondaire { color: #a9c4d7; }
QLabel#titreBloc { font-size: 17px; font-weight: 700; }
QLabel#etatBorne { font-size: 26px; font-weight: 800; }
QLabel#valeur { font-size: 29px; font-weight: 800; }
QLabel#valeurCompteur { font-size: 23px; font-weight: 800; }
QLabel#petit { font-size: 11px; color: #abc2d3; }
QFrame#rail { background: #edf3f5; border-radius: 22px; }
QFrame#rail QLabel { color: #345269; }
QFrame#rail QLabel#surTitre { color: #647f92; }
QFrame#rail QLabel#marque { background: #176baf; color: white; border-radius: 18px; font-size: 34px; font-weight: 900; padding: 9px; letter-spacing: 3px; }
QFrame#panneau { background: #112d44; border: 1px solid #35546b; border-radius: 18px; }
QFrame#hero { background: #18486a; border: 1px solid #5e9fc3; border-radius: 20px; }
QFrame#compteur { background: #17394f; border: 1px solid #3c5d73; border-radius: 14px; }
QFrame#place { background: #1a3549; border: 1px solid #587387; border-top: 4px solid #7993a6; border-radius: 12px; }
QFrame#place[ton=vert] { background: #163c3e; border-color: #4bbaa5; }
QFrame#place[ton=bleu] { background: #173e5c; border-color: #69b8ef; }
QFrame#place[ton=rouge] { background: #492f3b; border-color: #e98085; }
QFrame#place[ton=orange] { background: #453d30; border-color: #edb85a; }
QLabel#numeroPlace { font-size: 21px; font-weight: 800; }
QLabel#etatPlace { font-size: 12px; font-weight: 700; }
QLabel#presencePlace { font-size: 10px; color: #bfd0dc; }
QLabel#bandeau { border-radius: 11px; padding: 10px 14px; font-weight: 600; background: #173c4c; color: #83e5ca; }
QLabel#bandeau[ton=orange] { background: #493d27; color: #ffdc94; }
QLabel#bandeau[ton=rouge] { background: #4c303c; color: #ffb1b5; }
QLabel#simulation { border: 1px solid #aa863e; border-radius: 9px; padding: 8px 12px; color: #ffd68a; background: #342f25; }
QLabel[ton=vert] { color: #83e5ca; }
QLabel[ton=rouge] { color: #ff9ca3; }
QLabel[ton=orange] { color: #ffd183; }
QLabel[ton=bleu] { color: #89d4ff; }
QLabel[ton=neutre] { color: #bbcedb; }
QPushButton { border: 1px solid #52768f; border-radius: 11px; padding: 10px 14px; background: #244a64; color: #f0f7fc; font-weight: 600; min-height: 19px; }
QPushButton:hover { background: #325e7d; border-color: #8accf6; }
QPushButton:pressed { background: #143951; }
QPushButton:focus { border: 2px solid #ffc565; }
QPushButton:disabled { color: #9baab4; background: #293d4c; border-color: #465766; }
QPushButton#primaire { background: #237ec0; border-color: #79c5f4; }
QPushButton#primaire:hover { background: #2997df; }
QPushButton#primaire:disabled { background: #293d4c; border-color: #465766; }
QPushButton#navigation { text-align: left; background: transparent; color: #456075; border: 1px solid transparent; padding: 10px; }
QPushButton#navigation:hover { background: #dce7ec; }
QPushButton#navigation:checked { background: #176baf; color: #ffffff; border-color: #176baf; }
QPushButton#commandeRail { color: #183c57; background: #dce7ec; border-color: #b1c5d2; font-size: 12px; padding: 10px 5px; }
QPushButton#commandeRail:hover { background: #cadde8; }
QPushButton#commandeRail:disabled { color: #8799a6; background: #e6ecef; border-color: #d6e0e6; }
QPushButton#arret { background: #c73546; border: 2px solid #ed7781; border-radius: 15px; color: white; font-size: 18px; font-weight: 800; min-height: 53px; }
QPushButton#arret:hover { background: #e24858; }
QPushButton#arret:disabled { background: #936c76; border-color: #ae9299; color: #e4d9dc; }
QPushButton#outil { color: #456075; background: transparent; border-color: #bfced7; font-size: 11px; padding: 6px; }
QLineEdit, QSpinBox { background: #0d2538; color: #f0f7fc; border: 1px solid #52768f; border-radius: 10px; padding: 11px; selection-background-color: #277bb2; }
QLineEdit:focus, QSpinBox:focus { border: 2px solid #79c5f4; }
QSpinBox::up-button, QSpinBox::down-button { width: 22px; }
QTableWidget, QTreeWidget, QPlainTextEdit { background: #102a3f; alternate-background-color: #15334b; color: #e5f0f8; border: 1px solid #35546b; border-radius: 10px; gridline-color: #28495f; selection-background-color: #276a95; selection-color: white; }
QHeaderView::section { background: #20465f; color: #bdd9ea; padding: 11px; border: none; border-bottom: 1px solid #52768f; font-size: 11px; font-weight: 700; }
QTableWidget::item, QTreeWidget::item { padding: 6px; }
QTableWidget::item:selected, QTreeWidget::item:selected { background: #276a95; color: white; }
QTabWidget::pane { border: none; padding-top: 12px; }
QTabBar::tab { background: #16334a; color: #b1ccde; padding: 12px 22px; margin-right: 8px; border: 1px solid #3c5d73; border-radius: 9px; }
QTabBar::tab:selected { background: #236993; color: white; border-color: #78bce6; }
QScrollArea { background: transparent; border: none; }
QWidget#page { background: transparent; }
QScrollBar:vertical { background: #122b40; width: 10px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #4e7189; min-height: 25px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { color: #102a3f; background: #e5f0f8; border: 1px solid #70a2c5; padding: 6px; }
"""
