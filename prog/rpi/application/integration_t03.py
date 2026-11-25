"""Point de branchement du responsable T03 ; aucune reservation implementee ici."""

from api.identification import InterfaceIdentification, ModuleT03


def creer_module_t03(identification: InterfaceIdentification) -> ModuleT03 | None:
    """Quand T03 sera pret, retourner son module avec cet acces en lecture seule.

    Exemple de noms a adapter par le responsable T03 :
        from modules.reservation import ReservationT03
        return ReservationT03(identification=identification)

    Le module devra fournir actualiser(), comme indique dans INTERFACE_T03_T02.md.
    """
    return None
