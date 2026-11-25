"""Unique point de branchement du futur T04. Aucune demande automatique ici."""

from api.paiements import InterfacePaiement, ModuleT04


def creer_module_t04(paiements: InterfacePaiement) -> ModuleT04 | None:
    """Quand T04 sera pret, remplacer le retour par son constructeur.

    Exemple (module a fournir par le responsable T04) :
        from modules.facturation import FacturationT04
        return FacturationT04(paiements=paiements)

    T04 utilise seulement l'API de paiement et fournit actualiser().
    Aucun changement supplementaire a main.py ou au lecteur n'est necessaire.
    """
    return None
