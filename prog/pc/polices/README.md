# Polices embarquées

Ces fichiers sont chargés localement par `pc.holographie.charger_polices()`.
Aucune installation système ni connexion Internet n'est requise.

| Famille | Graisses livrées | Utilisation | Licence |
| --- | --- | --- | --- |
| Nunito | Regular 400, Bold 700, ExtraBold 800 | Texte, commandes, données | [OFL 1.1](Nunito-OFL.txt) |
| Fredoka | Medium 500, SemiBold 600, largeur 100 | Titres, numéros, emblème ESA | [OFL 1.1](Fredoka-OFL.txt) |

Sources : dépôt officiel [Google Fonts / Nunito](https://github.com/google/fonts/tree/main/ofl/nunito)
et [Google Fonts / Fredoka](https://github.com/google/fonts/tree/main/ofl/fredoka),
récupérées le 25 novembre 2026. Les crédits et licences complets accompagnent
les polices. Aucune police commerciale du film n'est redistribuée.

Les instances statiques sont générées depuis `Nunito[wght].ttf` et
`Fredoka[wdth,wght].ttf` avec FontTools pour que Qt sélectionne réellement les
graisses voulues sur Linux. Aucun glyphe n'a été redessiné. Exemple de génération
hors application :

```python
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

font = TTFont("Fredoka[wdth,wght].ttf")
instance = instantiateVariableFont(
    font, {"wght": 600, "wdth": 100}, updateFontNames=True,
)
instance.save("Fredoka-SemiBold.ttf")
```

FontTools n'est pas une dépendance de l'application.
