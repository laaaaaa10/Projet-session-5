"""
essai_depot.py - T03 + T05 (RPi) : séquence de dépôt complète jusqu'à la
barrière, branchée sur les modules réels déjà livrés par l'équipe :

  T02 (pont Qt)  : lecture de la carte RFID et solde du compte
  T03            : choix de la place, confirmation en 60 s, barrière
  T05            : billet imprimé par le STM32 Borne (CAN)
  T11            : ascenseur (STM32 Haut) jusqu'à la place, confirmation IR,
                   début de facturation

  Accueil → carte RFID (T02) → place (T03) → confirmation (T03)
          → billet (T05) → confirmation du billet → barrière ouverte (T03)
          → véhicule sur la rampe (IR entrée absent) → barrière fermée
          → T11 : prise, transport, dépôt, confirmation IR, retour au niveau 0

Les tâches non livrées sont simulées dans cette fenêtre : T01 (fenêtre
principale), T04 (création de la transaction), T06 (IR), T13 (hors service).

Options :
  --lecteur-reel     lecteur RFID du Pi (sinon boutons « carte » simulés)
  --simul-can        STM32 Borne et ascenseur simulés sur un bus virtuel (sinon can0)
  --simul-barriere   servo simulé (sinon PCA9685)

Projet ESA - 243-557 - Automne 2026
Auteur : Edwin (T03 / T05)
"""
import os
import random
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))   # racine prog/rpi

from PyQt6.QtCore import QEventLoop, QTimer                                          # noqa: E402
from PyQt6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QLabel,  # noqa: E402
                             QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from communications.can_bus import ServiceCAN                            # noqa: E402
from interface.qt.pages_billet import PageBillet                         # noqa: E402
from interface.qt.pages_reservation import (PageCarte,                   # noqa: E402
                                             PageConfirmationDepot, PageReservation)
from interface.qt.pont_t02 import PontT02Qt                              # noqa: E402
from modules.barriere import CommandeBarriere                            # noqa: E402
from modules.billets import creer_gestion_billets                        # noqa: E402
from modules.depot import creer_gestion_depot                            # noqa: E402
from modules.reservation import GestionReservation                       # noqa: E402
from modules.stationnement import (EtatPlace, ModeleStationnement,      # noqa: E402
                                   PLACES_PAR_ETAGE, Presence)

CARTES_DEMO = {"Carte Jason": "11008827F9", "Carte Lucia": "1100823734",
               "Carte inconnue": "AABBCCDDEE"}


def main():
    lecteur_reel = "--lecteur-reel" in sys.argv
    app = QApplication(sys.argv)
    donnees = TemporaryDirectory(prefix="esa-depot-")   # soldes de démonstration (copie)

    # --- Modèle partagé des places (alimenté par T06 en temps normal) ---------
    modele = ModeleStationnement()
    for n in range(1, 15):
        modele.changer_presence(n, Presence.ABSENT)
    for n in random.sample(range(1, 15), 4):
        modele.changer_etat(n, EtatPlace.OCCUPEE)
        modele.changer_presence(n, Presence.PRESENT)

    # --- Simulations des tâches non livrées -------------------------------------
    case_ir = QCheckBox("Véhicule devant la barrière (IR, T06)")
    case_hs = QCheckBox("Hors service (T13)")
    sessions = {"compteur": 0, "id": None, "cartes": {}, "depot": None}   # depot : (transaction, place)

    def conditions_confirmation():
        if case_hs.isChecked():
            return False, "système hors service"
        if not case_ir.isChecked():
            return False, "aucun véhicule détecté devant la barrière"
        return True, ""

    def conditions_barriere():
        return (False, "arrêt / hors service") if case_hs.isChecked() else (True, "")

    def creer_transaction(numero_place, session_id):          # T04 simulé
        transaction = random.randint(0, 999_999)
        carte = sessions["cartes"].get(session_id, "?")
        print(f"[T04] transaction {transaction:06d} : place {numero_place}, carte {carte}")
        return transaction

    # --- Modules réels -------------------------------------------------------------
    reservation = GestionReservation(modele, creer_transaction, conditions_confirmation)
    barriere = CommandeBarriere(simulation="--simul-barriere" in sys.argv,
                                verifier_securite=conditions_barriere)
    barriere.fermer()

    simulateurs = []
    simul_ascenseur = None
    if "--simul-can" in sys.argv:
        from exemples.simulateur_ascenseur import SimulateurAscenseur
        from exemples.simulateur_stm32_borne import SimulateurStm32Borne
        service_can = ServiceCAN(interface="virtual", channel="esa")
        simul_ascenseur = SimulateurAscenseur(channel="esa")
        simulateurs = [SimulateurStm32Borne(channel="esa"), simul_ascenseur]
        for simulateur in simulateurs:
            simulateur.demarrer()
    else:
        service_can = ServiceCAN()
    billets = creer_gestion_billets(service_can)

    def facturation(transaction_id, horodatage):                  # T04/T12 simulé
        print(f"[T04] facturation de {transaction_id:06d} démarrée à {horodatage:%H:%M:%S}")

    depot = creer_gestion_depot(service_can, modele, facturation)
    try:
        service_can.demarrer()
    except Exception as erreur:
        print(f"[CAN] bus indisponible ({erreur}) : le billet affichera « impression impossible »")

    pont = PontT02Qt(donnees.name, simulation=not lecteur_reel)

    # --- Pages ---------------------------------------------------------------------
    accueil = QPushButton("Toucher pour déposer une voiture")
    accueil.setStyleSheet("font-size: 28px; padding: 40px;")
    page_carte = PageCarte()
    page_choix = PageReservation(reservation)
    page_confirmation = PageConfirmationDepot(reservation)
    page_billet = PageBillet(billets)
    pages = QStackedWidget()
    for page in (accueil, page_carte, page_choix, page_confirmation, page_billet):
        pages.addWidget(page)

    pont.carte_lue.connect(page_carte.recevoir_carte)        # lecture RFID de T02

    def retour_accueil():
        if sessions["id"]:
            reservation.terminer_session(sessions["id"])
        pages.setCurrentWidget(accueil)

    def nouvelle_session():
        sessions["compteur"] += 1
        sessions["id"] = f"depot-{sessions['compteur']}"
        page_choix.session_id = page_confirmation.session_id = sessions["id"]
        pages.setCurrentWidget(page_carte)

    def carte_acceptee(info):
        sessions["cartes"][sessions["id"]] = info.id_uart
        pages.setCurrentWidget(page_choix)

    def depot_confirme(transaction_id, numero_place):
        sessions["depot"] = (transaction_id, numero_place)
        pages.setCurrentWidget(page_billet)
        page_billet.afficher_billet(transaction_id, numero_place)

    def billet_confirme(transaction_id):
        if barriere.ouvrir():
            print(f"[T03] billet {transaction_id:06d} confirmé : barrière ouverte")
        else:
            print(f"[T03] ouverture refusée : {barriere.derniere_raison}")
        QTimer.singleShot(2500, retour_accueil)

    def ir_change(present):
        if not present and barriere.est_ouverte():
            barriere.fermer()
            print("[T03] véhicule sur la rampe : barrière fermée")
            if sessions["depot"] is not None:
                transaction_id, numero_place = sessions["depot"]
                sessions["depot"] = None
                niveau = 1 + (numero_place - 1) // PLACES_PAR_ETAGE
                position = 1 + (numero_place - 1) % PLACES_PAR_ETAGE
                if depot.demarrer(transaction_id, niveau, position):
                    print(f"[T11] dépôt {transaction_id:06d} : niveau {niveau}, position {position}")
                else:
                    print(f"[T11] dépôt refusé : {depot.derniere_erreur}")

    accueil.clicked.connect(nouvelle_session)
    page_carte.annulee.connect(retour_accueil)
    page_carte.carte_acceptee.connect(carte_acceptee)
    page_choix.place_reservee.connect(lambda p: pages.setCurrentWidget(page_confirmation))
    page_confirmation.reservation_annulee.connect(retour_accueil)
    page_confirmation.reservation_expiree.connect(
        lambda: (print("[T03] réservation expirée : place libérée"), retour_accueil()))
    page_confirmation.depot_confirme.connect(depot_confirme)
    page_billet.billet_confirme.connect(billet_confirme)
    case_ir.toggled.connect(ir_change)

    # --- Panneau d'essai --------------------------------------------------------------
    etat_barriere = QLabel("")
    etat_t11 = QLabel("T11 : inactif")
    dernier_etat = {"t11": ""}

    def rafraichir():
        depot.mettre_a_jour()
        etat_barriere.setText(f"Barrière : {barriere.etat().value}")
        texte = depot.obtenir_etat()
        if texte != dernier_etat["t11"]:
            dernier_etat["t11"] = texte
            etat_t11.setText(f"T11 : {texte}")
            print(f"[T11] {texte}")

    minuterie = QTimer()
    minuterie.timeout.connect(rafraichir)
    minuterie.start(100)

    panneau = QHBoxLayout()
    if not lecteur_reel:
        for nom, id_uart in CARTES_DEMO.items():
            bouton = QPushButton(nom)
            bouton.clicked.connect(lambda _, i=id_uart: pont.simuler_badge(i))
            panneau.addWidget(bouton)
    panneau.addWidget(case_ir)
    panneau.addWidget(case_hs)
    panneau.addWidget(etat_barriere)

    panneau_t11 = QHBoxLayout()                    # 2e ligne : ascenseur (T11)
    panneau_t11.addWidget(etat_t11, 1)
    if simul_ascenseur is not None:
        case_sans_ir = QCheckBox("Place : pas de détection IR")
        case_sans_ir.toggled.connect(lambda coche: setattr(simul_ascenseur, "ir_actif", not coche))
        panneau_t11.addWidget(case_sans_ir)
    bouton_acquitter = QPushButton("Acquitter défaut T11")
    bouton_acquitter.clicked.connect(depot.acquitter_defaut)
    panneau_t11.addWidget(bouton_acquitter)

    centre = QWidget()
    disposition = QVBoxLayout(centre)
    disposition.addLayout(panneau)
    disposition.addLayout(panneau_t11)
    disposition.addWidget(pages)
    fenetre = QMainWindow()
    fenetre.setWindowTitle("Essai dépôt : T02 + T03 + T05")
    fenetre.setCentralWidget(centre)
    fenetre.resize(1000, 560)
    fenetre.show()

    pont.erreur.connect(lambda incident: print(f"[T02] {incident.action} : {incident.message}"))
    pont.demarrer()
    code = app.exec()

    # --- Libération du matériel ----------------------------------------------------------
    if pont.en_cours:                    # arrêt asynchrone de T02 : attendre « arrete »
        boucle = QEventLoop()
        pont.arrete.connect(boucle.quit)
        QTimer.singleShot(3000, boucle.quit)
        pont.arreter()
        boucle.exec()
    depot.arreter()
    barriere.liberer()
    service_can.arreter()
    for simulateur in simulateurs:
        simulateur.arreter()
    donnees.cleanup()
    sys.exit(code)


if __name__ == "__main__":
    main()
