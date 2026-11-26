"""Vrai broker Mosquitto sur boucle locale uniquement, pour les essais automatises."""

import os
from pathlib import Path
import shutil
import socket
import subprocess
from tempfile import TemporaryDirectory
import time


class BancBroker:
    def __init__(self, port=None):
        if port is None:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
        self.port = port
        self.processus = None
        self._dossier = None

    def demarrer(self):
        executable = os.environ.get("ESA_TEST_MOSQUITTO") or shutil.which("mosquitto")
        if not executable:
            raise RuntimeError("Installer Mosquitto 2.x pour les essais broker, ou definir ESA_TEST_MOSQUITTO")
        self._dossier = TemporaryDirectory(prefix="esa-t13-broker-")
        configuration = Path(self._dossier.name) / "mosquitto.conf"
        configuration.write_text(f"listener {self.port} 127.0.0.1\nallow_anonymous true\npersistence false\n",
                                 encoding="utf-8")
        self.processus = subprocess.Popen(
            [executable, "-c", str(configuration)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        limite = time.monotonic() + 5
        while time.monotonic() < limite:
            if self.processus.poll() is not None:
                self.fermer()
                raise RuntimeError("Le broker Mosquitto de test n'a pas demarre")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.02)
        self.fermer()
        raise TimeoutError("Broker local non disponible")

    def fermer(self):
        if self.processus is not None and self.processus.poll() is None:
            self.processus.terminate()
            try:
                self.processus.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.processus.kill()
                self.processus.wait(timeout=3)
        if self._dossier is not None:
            self._dossier.cleanup()
            self._dossier = None


if __name__ == "__main__":
    import argparse
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--broker", type=int, required=True, metavar="PORT")
    options = analyseur.parse_args()
    if not 1 <= options.broker <= 65535:
        analyseur.error("Le port doit etre entre 1 et 65535")
    broker = BancBroker(options.broker)
    try:
        broker.demarrer()
        print(f"Broker de test : 127.0.0.1:{broker.port}", flush=True)
        broker.processus.wait()
    except KeyboardInterrupt:
        pass
    finally:
        broker.fermer()
