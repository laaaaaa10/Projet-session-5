"""Client de l'acces T02 : affiche l'identification, sans reservation ni barriere."""

from api.identification import InterfaceIdentification


class ClientT03Exemple:
    def __init__(self, identification: InterfaceIdentification):
        self.identification = identification

    def actualiser(self) -> None:
        for lecture in self.identification.lire_identifications():
            if lecture.compte_connu:
                print(f"T03 EXEMPLE | Carte : {lecture.id_uart}"
                      f" | Solde : {lecture.solde_centimes} centimes", flush=True)
            else:
                print(f"T03 EXEMPLE | Carte inconnue : {lecture.id_uart}", flush=True)
        # Le vrai T03 n'utilise une lecture que si son ecran attend une carte.
        # Hors de cet ecran, il consomme et ignore ces lectures pour eviter de
        # reutiliser une ancienne presentation lors de l'ouverture de l'ecran.
