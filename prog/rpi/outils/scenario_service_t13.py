#!/usr/bin/env python3
"""Injecter un evenement local dans le banc de service T13 explicitement simule."""

import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exemples.systeme_t13_simule import SCENARIOS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donnees", type=Path, required=True,
                        help="Le meme dossier que serveur_t13.py --simuler-service")
    parser.add_argument("action", choices=SCENARIOS)
    args = parser.parse_args(argv)
    if not (args.donnees / "service-simule.sqlite3").is_file():
        parser.error("Demarrer d'abord le serveur avec --simuler-service dans ce dossier")
    chemin = args.donnees / "scenario-service.json"
    temporaire = chemin.with_name(chemin.name + "." + uuid4().hex + ".tmp")
    temporaire.write_text(json.dumps({"id": uuid4().hex, "action": args.action}), encoding="utf-8")
    temporaire.replace(chemin)
    print(f"SIMULATION : {args.action} ; verifier sa prise en compte dans le PC avant le prochain scenario.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
