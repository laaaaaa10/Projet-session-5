"""
reservation.py - T03 (RPi) : réservation temporaire d'une place au dépôt.

Règles (énoncé ESA et interface T03) :
  - une seule réservation active par session ; la place choisie est verrouillée
    (état « réservée ») contre une seconde réservation ;
  - 60 s pour confirmer ; à l'expiration ou à l'annulation, la place est libérée
    SEULEMENT si le dépôt n'a pas été confirmé ;
  - à la confirmation, les conditions sont revérifiées, puis T04 crée la transaction.

Aucune attente : le délai est contrôlé par mettre_a_jour(), appelée
périodiquement (QTimer dans l'interface).

Identification : la carte RFID est lue par T02 (signal carte_lue du pont Qt) ;
evaluer_carte() calcule le solde, le tarif et la durée maximale à afficher.

Projet ESA - 243-557 - Automne 2026
"""
import time

from modules.stationnement import EtatPlace, Presence, libelle_place, numero_place

DELAI_CONFIRMATION_S = 60.0      # configurable (énoncé : 60 s)

# Tarif affiché à l'identification. TODO(T04) : T04 est propriétaire des tarifs ;
# remplacer par la valeur fournie par T04 (même valeur que sur le billet T05).
TARIF_CENTIMES_PAR_MINUTE = 10
DUREE_MINIMALE_MIN = 1           # solde minimal accepté : une minute de stationnement


class InfoCarte:
    """Résultat de l'identification au dépôt : solde, tarif et durée maximale théorique."""

    def __init__(self, id_uart, solde_centimes, tarif=TARIF_CENTIMES_PAR_MINUTE):
        self.id_uart = id_uart
        self.solde_centimes = solde_centimes            # None = carte inconnue (T02)
        self.tarif_centimes_par_minute = tarif
        self.duree_max_min = (0 if solde_centimes is None or tarif <= 0
                              else solde_centimes // tarif)
        if solde_centimes is None:
            self.acceptee, self.raison = False, "carte inconnue"
        elif self.duree_max_min < DUREE_MINIMALE_MIN:
            self.acceptee, self.raison = False, "solde insuffisant"
        else:
            self.acceptee, self.raison = True, ""


def evaluer_carte(id_uart: str, solde_centimes, tarif=TARIF_CENTIMES_PAR_MINUTE) -> InfoCarte:
    """Évalue une carte lue par T02 (IdentificationCarte.id_uart / solde_centimes)."""
    return InfoCarte(id_uart, solde_centimes, tarif)


class _Reservation:
    def __init__(self, session_id, numero, t_debut):
        self.session_id = session_id
        self.numero = numero
        self.t_debut = t_debut
        self.confirmee = False
        self.transaction_id = None


class GestionReservation:
    """Réservation des places pour le dépôt (T03)."""

    def __init__(self, modele, creer_transaction, verifier_conditions=None,
                 delai_s=DELAI_CONFIRMATION_S, horloge=time.monotonic):
        """
        modele : ModeleStationnement partagé.
        creer_transaction(numero_place, session_id) -> int | None : fournie par T04
            (la séquence de dépôt associe la session à la carte présentée).
        verifier_conditions() -> (bool, str) : système en service, zone d'entrée
            prête, aucun arrêt verrouillé (fournie par la séquence / T13).
        """
        self._modele = modele
        self._creer_transaction = creer_transaction
        self._verifier = verifier_conditions
        self._delai = delai_s
        self._horloge = horloge
        self._reservations = {}          # session_id → _Reservation
        self.derniere_raison = ""

    # ------------------------------------------------------------ consultation
    def obtenir_places(self) -> dict:
        """{'E1.1': {'etat': EtatPlace, 'presence': Presence, 'selectionnable': bool}, ...}
        Lu dans le modèle partagé : aucune seconde source de vérité."""
        places = {}
        for numero, (etat, presence) in self._modele.copie().items():
            places[libelle_place(numero)] = {
                "etat": etat,
                "presence": presence,
                "selectionnable": self._selectionnable(etat, presence),
            }
        return places

    @staticmethod
    def _selectionnable(etat, presence):
        # Libre ET aucun véhicule détecté (sinon : incohérence à signaler, pas à réserver)
        return etat == EtatPlace.LIBRE and presence == Presence.ABSENT

    def temps_restant(self, session_id: str) -> float:
        """Secondes restantes pour confirmer (0 si aucune réservation en attente)."""
        res = self._reservations.get(session_id)
        if res is None or res.confirmee:
            return 0.0
        return max(0.0, self._delai - (self._horloge() - res.t_debut))

    def place_de(self, session_id: str):
        res = self._reservations.get(session_id)
        return libelle_place(res.numero) if res else None

    # --------------------------------------------------------------- réserver
    def reserver_place(self, place: str, session_id: str) -> bool:
        """Verrouille la place pour cette session. False si impossible (voir derniere_raison)."""
        try:
            numero = numero_place(place)
        except ValueError as erreur:
            return self._refuser(str(erreur))

        actuelle = self._reservations.get(session_id)
        if actuelle is not None and actuelle.confirmee:
            return self._refuser("dépôt déjà confirmé pour cette session")

        with self._modele.verrou:   # vérifier et verrouiller sans interruption
            etat, presence = self._modele.etat(numero), self._modele.presence(numero)
            if not self._selectionnable(etat, presence):
                return self._refuser(f"place {place} non disponible ({etat.value})")
            # Changement de place : l'ancienne réservation non confirmée est libérée
            if actuelle is not None:
                self._liberer(actuelle)
            self._modele.changer_etat(numero, EtatPlace.RESERVEE)

        self._reservations[session_id] = _Reservation(session_id, numero, self._horloge())
        self.derniere_raison = ""
        return True

    # -------------------------------------------------------------- confirmer
    def confirmer_depot(self, session_id: str):
        """Revérifie les conditions et obtient le numéro de transaction de T04.
        Retourne l'identifiant, ou None si les conditions ne sont pas remplies."""
        self.mettre_a_jour()                     # une réservation expirée n'est plus valide
        res = self._reservations.get(session_id)
        if res is None:
            self._refuser("aucune réservation active (expirée ou annulée)")
            return None
        if res.confirmee:
            return res.transaction_id            # déjà confirmé : même transaction

        if self._modele.etat(res.numero) != EtatPlace.RESERVEE:
            self._refuser("la place n'est plus réservée")
            return None
        if self._modele.presence(res.numero) != Presence.ABSENT:
            self._refuser("présence détectée dans la place")
            return None
        if self._verifier is not None:
            permis, raison = self._verifier()
            if not permis:
                self._refuser(raison)
                return None

        transaction_id = self._creer_transaction(res.numero, session_id)
        if transaction_id is None:
            self._refuser("transaction refusée par T04")
            return None

        res.confirmee = True                     # le minuteur de 60 s ne s'applique plus
        res.transaction_id = transaction_id
        self.derniere_raison = ""
        return transaction_id

    # ---------------------------------------------------------- annuler / expirer
    def annuler_reservation(self, session_id: str) -> bool:
        """Annulation par l'utilisateur : refusée si le dépôt est déjà confirmé."""
        res = self._reservations.get(session_id)
        if res is None:
            return self._refuser("aucune réservation à annuler")
        if res.confirmee:
            return self._refuser("dépôt déjà confirmé : annulation impossible ici")
        self._liberer(res)
        del self._reservations[session_id]
        self.derniere_raison = ""
        return True

    def expiration_reservation(self, session_id: str) -> None:
        """Libère la réservation expirée, SEULEMENT si elle n'a pas été confirmée."""
        res = self._reservations.get(session_id)
        if res is not None and not res.confirmee:
            self._liberer(res)
            del self._reservations[session_id]

    def mettre_a_jour(self) -> list:
        """À appeler périodiquement. Retourne les sessions qui viennent d'expirer."""
        maintenant = self._horloge()
        expirees = [s for s, r in self._reservations.items()
                    if not r.confirmee and maintenant - r.t_debut >= self._delai]
        for session_id in expirees:
            self.expiration_reservation(session_id)
        return expirees

    def terminer_session(self, session_id: str) -> None:
        """Fin du dépôt (barrière franchie) : oublie la session. La place reste
        réservée ; T11 la passera à « occupée » après confirmation IR."""
        self._reservations.pop(session_id, None)

    # ------------------------------------------------------------------ interne
    def _liberer(self, res):
        with self._modele.verrou:
            if self._modele.etat(res.numero) == EtatPlace.RESERVEE:
                self._modele.changer_etat(res.numero, EtatPlace.LIBRE)

    def _refuser(self, raison):
        self.derniere_raison = raison
        return False
