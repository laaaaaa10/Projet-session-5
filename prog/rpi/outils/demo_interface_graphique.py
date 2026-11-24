#!/usr/bin/env python3
"""Banc graphique T02 sur PC Linux ou Pi ; fichiers temporaires par defaut."""

import argparse
from contextlib import ExitStack
from pathlib import Path
import signal
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lecteur-reel", action="store_true", help="ouvrir le lecteur du Pi au lieu des boutons simules")
    parser.add_argument("--donnees", type=Path, help="dossier persistant ; sinon donnees temporaires")
    parser.add_argument("--port", default="/dev/ttyAMA0")
    parser.add_argument("--gpio", type=int, default=17)
    parser.add_argument("--chip", type=int, default=0)
    parser.add_argument("--delai-ms", type=float, default=500)
    args = parser.parse_args(argv)
    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication
        from interface.qt.fenetre_demo import FenetreDemoT02
        from interface.qt.pont_t02 import PontT02Qt
    except ModuleNotFoundError as erreur:
        print(f"Dependance manquante : {erreur.name}. Installer PyQt6 (voir INTERFACE_GRAPHIQUE_T02.md).",
              file=sys.stderr)
        return 1
    with ExitStack() as ressources:
        dossier = args.donnees
        if dossier is None:
            dossier = ressources.enter_context(TemporaryDirectory(prefix="esa-qt-"))
        app = QApplication([sys.argv[0]])
        app.setStyle("Fusion")
        pont = PontT02Qt(dossier, simulation=not args.lecteur_reel, options_lecteur={
            "port": args.port, "gpio": args.gpio, "chip": args.chip, "delai_ms": args.delai_ms,
        })
        fenetre = FenetreDemoT02(pont, donnees_temporaires=args.donnees is None)
        precedent = signal.signal(signal.SIGINT, lambda *_: fenetre.close())
        ressources.callback(signal.signal, signal.SIGINT, precedent)
        # Donner regulierement la main a Python pour prendre en compte Ctrl+C.
        reveil = QTimer()
        reveil.timeout.connect(lambda: None)
        reveil.start(150)
        fenetre.show()
        fenetre.demarrer()
        return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
