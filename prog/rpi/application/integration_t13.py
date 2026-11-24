"""Point de branchement du futur T13 a l'acces comptes de T02."""

from api.comptes import InterfaceComptes, ModuleT13


def creer_module_t13(comptes: InterfaceComptes) -> ModuleT13 | None:
    """Quand T13 sera pret, retourner son module avec cet acces.

    Exemple de noms a adapter :
        from modules.supervision import SupervisionT13
        return SupervisionT13(comptes=comptes)

    Le futur module fournit actualiser(). Aucun client MQTT n'est lance ici.
    """
    return None
