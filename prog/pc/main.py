#!/usr/bin/env python3
"""Application PC de supervision. Le journal conserve les ID apres redemarrage."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", required=True, type=Path)
    parser.add_argument("--fenetre", action="store_true", help="Démarrer en fenêtre (plein écran par défaut, F11 pour basculer)")
    args = parser.parse_args(argv)
    from PyQt6.QtWidgets import QApplication
    from commun.t13.configuration import ConfigurationMQTT
    from pc.interface import FenetreSupervision, PontPC
    config = ConfigurationMQTT.depuis_environnement()
    app = QApplication(sys.argv[:1])
    pont = PontPC(config, args.journal)
    fenetre = FenetreSupervision(pont)
    if args.fenetre:
        fenetre.show()
    else:
        fenetre.showFullScreen()
    pont.thread.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
