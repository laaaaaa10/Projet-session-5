"""Journal PC des demandes immuables, distinct des comptes de T02."""

from pathlib import Path
import sqlite3

from commun.t13.protocole import decoder, encoder, valider_commande


class JournalDemandes:
    def __init__(self, chemin, cible):
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(chemin)
        self.db.execute("PRAGMA synchronous=FULL")
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS contexte (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS demandes (id TEXT PRIMARY KEY, contenu BLOB NOT NULL, reponse BLOB, termine INTEGER NOT NULL DEFAULT 0)")
            self.db.execute("INSERT OR IGNORE INTO contexte VALUES ('cible', ?)", (cible,))
        if self.db.execute("SELECT valeur FROM contexte WHERE cle='cible'").fetchone()[0] != cible:
            self.db.close()
            raise ValueError("Ce journal PC appartient a un autre broker/prefixe ; verifier la cible")

    def ajouter(self, demande):
        valider_commande(demande)
        identifiant, contenu = demande["id_commande"], encoder(demande)
        ancien = self.demande(identifiant)
        if ancien is not None and ancien != demande:
            raise ValueError("ID deja utilise avec une autre demande")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO demandes(id, contenu) VALUES (?, ?)", (identifiant, contenu))

    def demande(self, identifiant):
        ligne = self.db.execute("SELECT contenu FROM demandes WHERE id=?", (identifiant,)).fetchone()
        return None if ligne is None else decoder(ligne[0])

    def en_attente(self):
        return [decoder(l[0]) for l in self.db.execute("SELECT contenu FROM demandes WHERE termine=0 ORDER BY rowid")]

    def enregistrer_reponse(self, message):
        # Une acceptation retardee ne remplace pas un resultat final deja recu.
        finale = message["phase"] in {"TERMINEE", "REFUSEE"}
        with self.db:
            self.db.execute("UPDATE demandes SET reponse=?, termine=? WHERE id=? AND termine=0",
                            (encoder(message), int(finale), message["id_commande"]))

    def reprendre(self, identifiant):
        demande = self.demande(identifiant)
        if demande is None:
            raise ValueError("Demande absente du journal PC")
        with self.db:
            self.db.execute("UPDATE demandes SET termine=0, reponse=NULL WHERE id=?", (identifiant,))
        return demande

    def historique(self):
        return [{"demande": decoder(d), "reponse": None if r is None else decoder(r), "termine": bool(t)}
                for d, r, t in self.db.execute("SELECT contenu, reponse, termine FROM demandes ORDER BY rowid DESC LIMIT 100")]

    def fermer(self):
        self.db.close()
