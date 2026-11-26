"""Surfaces de verre, capsules et pictogrammes de la console ESA.

Décor purement graphique : aucune animation n'indique un état ou un progrès fictif.
Les polices sont embarquées ; le rendu ne nécessite aucun accès réseau.
"""

from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap, QRadialGradient,
)
from PyQt6.QtWidgets import QFrame, QWidget

_POLICES_CHARGEES = False


def charger_polices():
    global _POLICES_CHARGEES
    if not _POLICES_CHARGEES:
        for nom in ("Nunito-Regular.ttf", "Nunito-Bold.ttf", "Nunito-ExtraBold.ttf",
                    "Fredoka-Medium.ttf", "Fredoka-SemiBold.ttf"):
            QFontDatabase.addApplicationFont(str(Path(__file__).with_name("polices") / nom))
        _POLICES_CHARGEES = True


def couleur(valeur, alpha=255):
    c = QColor(valeur)
    c.setAlpha(alpha)
    return c


def trace(p, teinte, largeur=1):
    stylo = QPen(QColor(teinte), largeur)
    stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
    stylo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(stylo)


class FondConsole(QWidget):
    """Lumière bleue et courbes de projection derrière les panneaux flottants."""
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        fond = QLinearGradient(0, 0, w, h)
        for position, teinte in ((0, "#071b5a"), (.48, "#10467f"), (1, "#081937")):
            fond.setColorAt(position, QColor(teinte))
        p.fillRect(self.rect(), fond)
        for x, y, rayon, teinte in ((.62, -.1, .85, "#008eff"), (1.06, .7, .6, "#763bff"), (.1, 1.05, .8, "#00dfed")):
            halo = QRadialGradient(QPointF(w*x, h*y), w*rayon)
            halo.setColorAt(0, couleur(teinte, 100))
            halo.setColorAt(1, couleur(teinte, 0))
            p.fillRect(self.rect(), halo)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Grandes ellipses, comme les courbes architecturales de l'Axiom.
        for decalage in (0, 18, 56):
            trace(p, couleur("#a6faff", 22 if decalage else 43), 1.3)
            p.drawEllipse(QRectF(w*.23-decalage, -h*.64-decalage, w*1.12+2*decalage, h*1.15+2*decalage))
        trace(p, couleur("#88f4ff", 24), 2)
        p.drawEllipse(QRectF(w*.32, h*.76, w*.95, h*.5))
        p.end()


class PanneauHolographique(QFrame):
    """Verre teinté avec bord lumineux et reflet courbe, sans effet coûteux."""
    def __init__(self, mode="panneau"):
        super().__init__()
        self.mode = mode
        self.setObjectName(mode)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        zone = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        mode = self.mode
        accent = {"vert": "#50ffcd", "bleu": "#66daff", "rouge": "#ff6b9d",
                  "orange": "#ffdc64", "neutre": "#a5d2ed"}.get(self.property("ton"), "#67eaff")
        rayon = min(zone.height()/2, 40 if mode in ("place", "hero", "rail") else 32)
        chemin = QPainterPath()
        chemin.addRoundedRect(zone, rayon, rayon)
        # Le léger halo reste à l'intérieur du widget : pas de découpage par les scroll areas.
        for largeur, alpha in ((5, 14), (3, 26)):
            trace(p, couleur(accent, alpha), largeur)
            p.drawPath(chemin)
        fond = QLinearGradient(zone.topLeft(), zone.bottomRight())
        if mode == "rail":
            stops = ((0, "#f8feff", 255), (.42, "#ccefff", 250), (1, "#91badc", 250))
        elif mode == "hero":
            stops = ((0, "#26a8e6", 195), (.45, "#176aca", 170), (1, "#13386c", 215))
        elif mode == "place":
            stops = ((0, accent, 60), (.40, "#285679", 185), (1, "#152e55", 210))
        elif mode == "compteur":
            stops = ((0, accent, 46), (.55, "#174478", 190), (1, "#112c60", 200))
        else:
            stops = ((0, "#3395ca", 92), (.5, "#1c4e8c", 130), (1, "#0d2856", 190))
        for position, teinte, alpha in stops:
            fond.setColorAt(position, couleur(teinte, alpha))
        p.fillPath(chemin, fond)
        p.setClipPath(chemin)
        # Reflet en dôme : sommet blanc, disparition progressive dans le verre.
        reflet = QLinearGradient(0, zone.top(), 0, zone.top()+min(65, zone.height()*.6))
        reflet.setColorAt(0, couleur("#ffffff", 54 if mode != "rail" else 140))
        reflet.setColorAt(1, couleur("#ffffff", 0))
        p.fillPath(chemin, reflet)
        if mode in ("hero", "panneau"):
            trace(p, couleur("#a6faff", 14), 1)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(zone.right()-zone.width()*.42, -zone.height()*.55, zone.width()*.65, zone.height()*1.1))
        p.setClipping(False)
        bord = QLinearGradient(zone.topLeft(), zone.bottomRight())
        bord.setColorAt(0, couleur("#f3ffff", 230 if mode == "rail" else 150))
        bord.setColorAt(.4, couleur(accent, 80))
        bord.setColorAt(1, couleur(accent, 155))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(bord, 1.2))
        p.drawPath(chemin)
        if mode == "place":
            # Témoin distinct du décor : gris lorsque l'état est inconnu/périmé.
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(couleur(accent, 40))
            p.drawEllipse(QPointF(zone.center().x(), zone.top()+9), 7, 4)
            p.setBrush(QColor(accent))
            p.drawEllipse(QPointF(zone.center().x(), zone.top()+9), 3.5, 2)
        p.end()


class EmblemeESA(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(80)
        self.setAccessibleName("ESA — stationnement automatisé")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self.width()/2-85, 0)
        halo = QRadialGradient(QPointF(85, 42), 80)
        halo.setColorAt(0, couleur("#009fff", 120))
        halo.setColorAt(1, couleur("#009fff", 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QRectF(0, 0, 170, 80))
        bulle = QLinearGradient(0, 9, 0, 72)
        for stop, hexcode in ((0, "#a9fcff"), (.24, "#22b9f5"), (.55, "#0560d7"), (1, "#163e96")):
            bulle.setColorAt(stop, QColor(hexcode))
        p.setBrush(bulle)
        trace(p, "#f3ffff", 2)
        p.drawEllipse(QRectF(20, 8, 130, 62))
        p.save()
        p.translate(85, 40)
        p.rotate(-15)
        p.setBrush(Qt.BrushStyle.NoBrush)
        trace(p, couleur("#edffff", 230), 3)
        p.drawEllipse(QRectF(-81, -23, 162, 46))
        p.restore()
        font = QFont("Fredoka", 27, QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor("#073b91"))
        p.drawText(QRectF(20, 12, 130, 60), Qt.AlignmentFlag.AlignCenter, "ESA")
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(20, 9, 130, 60), Qt.AlignmentFlag.AlignCenter, "ESA")
        p.end()


def icone_bulle(motif, teinte="#16baf4"):
    """Pictogramme vectoriel dans une bulle : pas de glyphe dépendant du système."""
    pixmap = QPixmap(80, 80)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(2, 2)
    fond = QLinearGradient(0, 2, 0, 38)
    fond.setColorAt(0, QColor(teinte).lighter(155))
    fond.setColorAt(.45, QColor(teinte))
    fond.setColorAt(1, QColor(teinte).darker(180))
    p.setBrush(fond)
    trace(p, couleur("#ffffff", 170), 1)
    p.drawEllipse(QRectF(2, 2, 36, 36))
    p.setBrush(Qt.BrushStyle.NoBrush)
    trace(p, "#ffffff", 2)
    if motif == "plan":
        for x, y in ((12, 12), (22, 12), (12, 22), (22, 22)):
            p.drawRoundedRect(QRectF(x, y, 6, 6), 2, 2)
    elif motif == "carte":
        p.drawRoundedRect(QRectF(10, 12, 20, 16), 4, 4)
        p.drawLine(11, 18, 29, 18)
        p.drawLine(15, 23, 18, 23)
    elif motif == "activite":
        chemin = QPainterPath(QPointF(9, 22))
        for x, y in ((14, 22), (17, 14), (22, 27), (26, 18), (31, 18)):
            chemin.lineTo(x, y)
        p.drawPath(chemin)
    elif motif == "stats":
        for x, y in ((13, 23), (20, 15), (27, 10)):
            p.drawLine(x, y, x, 29)
    elif motif == "diagnostic":
        p.drawEllipse(QRectF(11, 10, 14, 14))
        p.drawLine(23, 23, 29, 29)
        p.drawLine(18, 14, 18, 20)
        p.drawLine(15, 17, 21, 17)
    p.end()
    return QIcon(pixmap)
