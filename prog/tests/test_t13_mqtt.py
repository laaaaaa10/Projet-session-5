"""T13 avec transport simule, mais vrais comptes CSV et journal PC SQLite."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PROG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROG))
sys.path.insert(0, str(PROG / "rpi"))

from application.acces_comptes import AccesComptes
from commun.t13.configuration import ConfigurationMQTT
from commun.t13.protocole import ACTIONS_SERVICE, canal_commande, canal_reponse, decoder, encoder, nouvelle_commande, repartir_etat, reponse
from commun.t13.transport import MessageMQTT
from modules.supervision import SupervisionT13
from pc.client import ClientSupervision
from pc.demandes import JournalDemandes
from stockage import comptes_csv as stockage
from test_comptes_transactions import BancComptes, INCONNU, JASON, LUCIA


class Horloge:
    def __init__(self):
        self.temps = 0.0

    def __call__(self):
        return self.temps


class TransportSimule:
    def __init__(self):
        self.config = ConfigurationMQTT("localhost", 1883, "esa/Equipe_1", False)
        self.etat = (True, 1, "")
        self.file, self.publications = [], []
        self.pair = None
        self.perdre_reponses = False
        self.ferme = False

    def publier(self, nom, valeur, *, retenir=False):
        self.publications.append((nom, deepcopy(valeur), retenir))
        if self.pair is not None and self.pair.etat[0] and not (nom.endswith("/reponse") and self.perdre_reponses):
            self.pair.file.append(MessageMQTT(self.config.topic(nom), encoder(valeur)))
        return self.etat[0]

    def recevoir(self, maximum=8):
        messages, self.file = self.file[:maximum], self.file[maximum:]
        return messages

    def fermer(self):
        self.ferme = True
        self.etat = (False, self.etat[1], "Ferme")


class TestsT13(BancComptes):
    def setUp(self):
        super().setUp()
        self.horloge = Horloge()
        self.pi, self.pc = TransportSimule(), TransportSimule()
        self.pi.pair, self.pc.pair = self.pc, self.pi
        self.supervision = SupervisionT13(AccesComptes(self.service), self.pi, horloge=self.horloge)
        self.chemin_journal = self.racine / "pc.sqlite3"
        self.journal = JournalDemandes(self.chemin_journal, "essai")
        self.addCleanup(lambda: self.journal.fermer())
        self.client = ClientSupervision(self.pc, self.journal, horloge=self.horloge)
        self.tour()
        self.assertTrue(self.client.frais)

    def tour(self):
        self.client.actualiser()
        self.supervision.actualiser()
        self.client.actualiser()

    def injecter(self, demande, *, retenu=False):
        self.pi.file.append(MessageMQTT(self.pi.config.topic(canal_commande(demande["commande"])), encoder(demande), retenu))
        self.supervision.actualiser()
        return [d for nom, d, _ in self.pi.publications if nom.endswith("/reponse")
                and d["id_commande"] == demande.get("id_commande")]

    def test_credit_et_reponse_correlée_avec_acceptation_distincte(self):
        reference = self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        self.assertEqual(len(self.lignes_journal()), 0)
        self.assertEqual(self.journal.demande(reference)["id_commande"], reference)
        self.tour()
        messages = [d for nom, d, _ in self.pi.publications if nom.endswith("/reponse") and d["id_commande"] == reference]
        self.assertEqual([d["phase"] for d in messages], ["ACCEPTEE", "TERMINEE"])
        self.assertEqual(messages[-1]["donnees"]["recu"]["id_transaction"], reference)
        self.assertEqual(self.solde(), 2500)
        self.assertEqual(self.client.etat["soldes"][JASON], 2500)
        self.assertEqual(self.journal.en_attente(), [])

    def test_inconnue_et_solde_zero_distincts(self):
        self.service.payer("vider", JASON, 2000)
        for carte, solde, code in ((JASON, 0, "SOLDE"), (INCONNU, None, "COMPTE_INCONNU")):
            reponses = self.injecter(nouvelle_commande("CONSULTER_SOLDE", id_uart=carte))
            self.assertEqual(reponses[-1]["code"], code)
            self.assertEqual(reponses[-1]["donnees"]["solde_centimes"], solde)

    def test_credit_repete_et_conflits_sans_nouveau_mouvement(self):
        demande = nouvelle_commande("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        self.injecter(demande)
        self.assertTrue(self.injecter(demande)[-1]["donnees"]["recu"]["deja_traitee"])
        for params in ({"id_uart": LUCIA, "montant_centimes": 500}, {"id_uart": JASON, "montant_centimes": 600}):
            modifiee = dict(demande, parametres=params)
            self.assertEqual(self.injecter(modifiee)[-1]["code"], "CONFLIT_TRANSACTION")
        self.assertEqual(self.solde(), 2500)
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_id_de_paiement_partage_rejete(self):
        demande = nouvelle_commande("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        self.service.payer(demande["id_commande"], JASON, 500)
        self.assertEqual(self.injecter(demande)[-1]["code"], "CONFLIT_TRANSACTION")
        self.assertEqual(self.solde(), 1500)

    def test_commandes_invalides_retenues_et_json_malformes_sans_ecriture(self):
        base = nouvelle_commande("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        invalides = [dict(base, version=True), dict(base, inconnu=1),
                     dict(base, parametres=[]), dict(base, id_commande="credit-sans-prefixe")]
        invalides += [dict(base, parametres={"id_uart": JASON, "montant_centimes": m})
                      for m in (True, False, 0, -1, "500", 5.0, None)]
        invalides += [dict(base, parametres={"id_uart": carte, "montant_centimes": 500})
                      for carte in ("008827F9", "0008923129X", "Jason", None, 123)]
        for demande in invalides:
            self.injecter(demande)
        self.injecter(base, retenu=True)
        for donnees in (b"{", b"[]", b'{"version":1,"version":1}', b"null", b'\xff'):
            self.pi.file.append(MessageMQTT(self.pi.config.topic("commande"), donnees))
        self.supervision.actualiser()
        self.assertEqual(len(self.lignes_journal()), 0)
        self.assertEqual(self.solde(), 2000)
        self.assertGreaterEqual(self.supervision.messages_invalides, len(invalides) + 6)

    def test_erreur_stockage_issue_inconnue_et_reprise_meme_id(self):
        reference = self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        with patch.object(stockage, "_ecrire_comptes", side_effect=OSError("interruption")):
            self.tour()
        self.assertEqual(self.journal.historique()[0]["reponse"]["phase"], "INCERTAINE")
        self.assertEqual(len(self.journal.en_attente()), 1)
        self.horloge.temps += 4
        with self.assertLogs(stockage.JOURNAL_TECHNIQUE, level="WARNING"):
            self.tour()
        recu = self.journal.historique()[0]["reponse"]["donnees"]["recu"]
        self.assertEqual(recu["id_transaction"], reference)
        self.assertTrue(recu["deja_traitee"])
        self.assertEqual(self.solde(), 2500)
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_perte_reponse_redemarrage_pc_pi_retrouve_meme_credit(self):
        reference = self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        contenu = self.journal.demande(reference)
        self.pi.perdre_reponses = True
        self.tour()
        self.assertEqual(self.solde(), 2500)
        self.journal.fermer()
        self.journal = JournalDemandes(self.chemin_journal, "essai")
        self.assertEqual(self.journal.demande(reference), contenu)
        self.client = ClientSupervision(self.pc, self.journal, horloge=self.horloge)
        self.supervision = SupervisionT13(AccesComptes(self.nouveau_service()), self.pi, horloge=self.horloge)
        self.pi.perdre_reponses = False
        self.tour()
        self.tour()
        self.assertTrue(self.journal.historique()[0]["reponse"]["donnees"]["recu"]["deja_traitee"])
        self.assertEqual(self.solde(), 2500)
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_recu_historique_et_snapshot_courant_separes(self):
        demande = nouvelle_commande("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        self.injecter(demande)
        self.service.payer("paiement", JASON, 1000)
        recu = self.injecter(demande)[-1]["donnees"]["recu"]
        self.assertEqual(recu["solde_apres_centimes"], 2500)
        self.assertEqual(self.supervision.instantane()["soldes"][JASON], 1500)

    def test_deconnexion_resynchronisation_et_donnees_perimees(self):
        ancien = deepcopy(self.client.etat)
        self.pc.etat = (False, 1, "coupure")
        self.client.actualiser()
        self.assertFalse(self.client.frais)
        self.service.crediter("credit-local", JASON, 100)
        self.pc.etat = (True, 2, "")
        self.pc.file.append(MessageMQTT(self.pc.config.topic("etat"), encoder(ancien), True))
        self.client.actualiser()
        self.assertFalse(self.client.frais)
        self.tour()
        self.assertTrue(self.client.frais)
        self.assertEqual(self.client.etat["soldes"][JASON], 2100)
        self.horloge.temps += 16
        self.assertFalse(self.client.frais)
        with self.assertRaises(ValueError):
            self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)

    def test_reponse_non_correlée_et_acceptation_ne_cloturent_pas(self):
        reference = self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        demande = self.journal.demande(reference)
        messages = [reponse(nouvelle_commande("CONSULTER_SOLDE", id_uart=JASON), "TERMINEE", "SOLDE"),
                    reponse(dict(demande, commande="CONSULTER_SOLDE"), "TERMINEE", "SOLDE"),
                    reponse(demande, "ACCEPTEE", "DEMANDE_VALIDEE")]
        for message in messages:
            self.pc.file.append(MessageMQTT(self.pc.config.topic(canal_reponse(message["commande"])), encoder(message)))
        self.client.actualiser()
        self.assertEqual(len(self.journal.en_attente()), 1)
        self.assertEqual(self.journal.historique()[0]["reponse"]["phase"], "ACCEPTEE")

    def test_recu_incompatible_avec_carte_ou_montant_ne_cloture_pas(self):
        reference = self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        demande = self.journal.demande(reference)
        recu = {"id_transaction": reference, "id_uart": LUCIA, "montant_centimes": 500,
                "type_operation": "CREDIT", "statut": "CREDITE", "deja_traitee": False}
        message = reponse(demande, "TERMINEE", "CREDITE", {"recu": recu})
        self.pc.file.append(MessageMQTT(self.pc.config.topic(canal_reponse(message["commande"])), encoder(message)))
        self.client.actualiser()
        self.assertEqual(len(self.journal.en_attente()), 1)
        self.assertEqual(self.client.messages_invalides, 1)

    def test_credit_inconnu_refus_durable_sans_compte_cree(self):
        demande = nouvelle_commande("AJOUTER_CREDIT", id_uart=INCONNU, montant_centimes=500)
        self.assertEqual(self.injecter(demande)[-1]["code"], "COMPTE_INCONNU")
        self.assertTrue(self.injecter(demande)[-1]["donnees"]["recu"]["deja_traitee"])
        self.assertIsNone(self.service.consulter_compte(INCONNU))
        self.assertEqual(len(self.lignes_journal()), 1)

    def test_journal_immutable_et_pas_de_nouvel_id_si_credit_en_attente(self):
        reference = self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        demande = self.journal.demande(reference)
        with self.assertRaises(ValueError):
            self.journal.ajouter(dict(demande, parametres={"id_uart": JASON, "montant_centimes": 600}))
        with self.assertRaises(ValueError):
            self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        with self.assertRaises(ValueError):
            JournalDemandes(self.chemin_journal, "autre-borne")
        self.assertEqual(self.journal.demande(reference), demande)

    def test_journal_pc_indisponible_empeche_premier_envoi(self):
        nombre = len(self.pc.publications)
        with patch.object(self.journal, "ajouter", side_effect=OSError("disque plein")):
            with self.assertRaises(OSError):
                self.client.demander("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        self.tour()
        self.assertEqual(len(self.pc.publications), nombre)
        self.assertEqual(len(self.lignes_journal()), 0)

    def test_commandes_systeme_refusees_sans_fausse_confirmation(self):
        for action in ACTIONS_SERVICE:
            messages = self.injecter(nouvelle_commande(action))
            self.assertEqual([(m["phase"], m["code"]) for m in messages],
                             [("REFUSEE", "MODULE_INDISPONIBLE")])
        etat = self.supervision.instantane()
        self.assertEqual(len(etat["places"]), 14)
        self.assertTrue(all(p["logique"] == "INCONNU" for p in etat["places"]))
        self.assertIsNone(etat["arret_verrouille"])
        self.assertIsNone(etat["transactions"])
        self.assertIsNone(etat["statistiques"])

    def test_commande_inconnue_reponse_refusee_correlée(self):
        demande = dict(nouvelle_commande("SYNCHRONISER"), commande="DEBITER")
        messages = self.injecter(demande)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["id_commande"], demande["id_commande"])
        self.assertEqual((messages[0]["phase"], messages[0]["code"]), ("REFUSEE", "MESSAGE_INVALIDE"))
        self.assertEqual(self.lignes_journal(), [])

    def test_actualisation_bornee_et_aucun_traitement_callback(self):
        demande = nouvelle_commande("CONSULTER_SOLDE", id_uart=JASON)
        self.pi.file = [MessageMQTT(self.pi.config.topic(canal_commande(demande["commande"])), encoder(demande)) for _ in range(20)]
        self.supervision.actualiser()
        self.assertEqual(len(self.pi.file), 12)

    def test_credit_sur_topic_general_refuse_sans_mouvement(self):
        demande = nouvelle_commande("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        self.pi.file.append(MessageMQTT(self.pi.config.topic("commande"), encoder(demande)))
        self.supervision.actualiser()
        reponses = [d for nom, d, _ in self.pi.publications if nom == "comptes/reponse"
                    and d["id_commande"] == demande["id_commande"]]
        self.assertEqual(reponses[-1]["code"], "MESSAGE_INVALIDE")
        self.assertEqual(self.lignes_journal(), [])

    def test_publications_distinctes_sans_melanger_les_revisions(self):
        sujets = {nom for nom, _, _ in self.pi.publications}
        self.assertTrue({"etat", "places", "anomalies", "transactions"} <= sujets)
        ancienne = deepcopy(self.client.etat)
        a = repartir_etat(self.supervision.instantane())
        self.service.crediter("credit-local", JASON, 100)
        b = repartir_etat(self.supervision.instantane())
        def recevoir(nom, valeur):
            self.pc.file.append(MessageMQTT(self.pc.config.topic(nom), encoder(valeur)))
        for nom in ("etat", "places"):
            recevoir(nom, a[nom])
        for nom in ("anomalies", "transactions"):
            recevoir(nom, b[nom])
        self.client.actualiser()
        self.assertEqual(self.client.etat, ancienne)
        for nom in ("etat", "places"):
            recevoir(nom, b[nom])
        self.client.actualiser()
        self.assertEqual(self.client.etat["revision"], b["etat"]["revision"])
        self.assertEqual(self.client.etat["soldes"][JASON], 2100)

    def test_ancien_champ_id_demande_refuse_sans_credit(self):
        demande = nouvelle_commande("AJOUTER_CREDIT", id_uart=JASON, montant_centimes=500)
        demande["id_demande"] = demande.pop("id_commande")
        self.injecter(demande)
        self.assertEqual(self.lignes_journal(), [])


class TestsConfiguration(unittest.TestCase):
    def test_huit_topics_imposes_et_isolation_de_cinq_equipes(self):
        suffixes = {"etat", "places", "anomalies", "transactions", "commande/reponse",
                    "comptes/reponse", "commande", "comptes/commande"}
        equipes = []
        for equipe in range(1, 6):
            config = ConfigurationMQTT("localhost", 1883, f"esa/Equipe_{equipe}/", False)
            topics = {config.topic(s) for s in suffixes}
            self.assertEqual(topics, {f"esa/Equipe_{equipe}/{s}" for s in suffixes})
            self.assertTrue(all(not topics & autre for autre in equipes))
            equipes.append(topics)
        for prefixe in ("esa/equipe_1", "esa/Equipe_0", "esa/Equipe_6", "esa/Equipe_1/x"):
            with self.assertRaises(ValueError):
                ConfigurationMQTT("localhost", 1883, prefixe, False)
        with self.assertRaises(ValueError):
            config.topic("disponibilite")

    def test_aucun_broker_implicite_ni_mot_de_passe_dans_repr(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ValueError):
            ConfigurationMQTT.depuis_environnement()
        config = ConfigurationMQTT("exemple.invalid", 8883, "esa/Equipe_1", True, "utilisateur", "secret-test")
        self.assertNotIn("secret-test", repr(config))
        for port in (True, 0, 65536):
            with self.assertRaises(ValueError):
                ConfigurationMQTT("localhost", port, "esa/Equipe_1", False)
        for prefixe in ("", "test/#", "test/+", "/test", "test/"):
            with self.assertRaises(ValueError):
                ConfigurationMQTT("localhost", 1883, prefixe, False)


if __name__ == "__main__":
    unittest.main()
