# PDF 4-up Saddle Imposer

Petit outil Python pour transformer un PDF exporté depuis InDesign en un PDF A4 imposé :

- 4 pages par face A4
- 8 pages par feuille recto-verso
- ordre piqûre à cheval
- repères de coupe
- repères de pliage
- gestion du fond perdu si le PDF source contient du vrai fond perdu

## Installation avec uv

```bash
uv sync
```

Puis :

```bash
uv run pdf4up-saddle --help
```

### Dépannage (si `uv sync` échoue au build)

Si vous voyez une erreur Hatchling du type *"Unable to determine which files to ship inside the wheel"*,
assurez-vous que `pyproject.toml` contient bien :

- un package Python réel dans `src/` (ex. `src/pdf4upimposer/__init__.py`)
- et une config wheel explicite :

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/pdf4upimposer"]
```

## Export conseille depuis InDesign

Exportez un PDF en pages simples, dans l'ordre normal : 1, 2, 3, 4...

Pour un flux pro avec fond perdu :

1. Dans InDesign, définissez le fond perdu du document, par exemple 3 mm.
2. Exportez en Adobe PDF.
3. Dans `Marks and Bleeds`, activez `Use Document Bleed Settings`.
4. Évitez d'inclure les marques d'impression InDesign si ce script doit les générer.

Le script peut lire les boîtes PDF (TrimBox, BleedBox, etc.). Le fond perdu doit déjà exister dans le PDF source.
Le script ne peut pas inventer de l'image au-delà du bord si le PDF a été exporté sans fond perdu.

## Inspecter un PDF

```bash
uv run pdf4up-saddle inspect mag.pdf
```

Si votre PDF ne contient pas de TrimBox fiable, indiquez la taille finie manuellement :

```bash
uv run pdf4up-saddle inspect mag.pdf --trim-size-mm 125x85
```

## Generer un PDF impose A4

Pour un magazine fini de 12,5 cm x 8,5 cm :

```bash
uv run pdf4up-saddle impose mag.pdf magazine_A4_impose.pdf --trim-size-mm 125x85 --sheet-orientation landscape --bleed-mm 3 --labels --debug-boxes
```

Vérifiez d'abord avec `--labels --debug-boxes`. Quand l'ordre et l'orientation sont bons :

```bash
uv run pdf4up-saddle impose mag.pdf magazine_A4_impose.pdf --trim-size-mm 125x85 --sheet-orientation landscape --bleed-mm 3
```

## Debug & diagnostic

- `--debug-boxes` : dessine des rectangles de contrôle sur le PDF imposé
  - bleu = la zone Trim cible
  - rouge = la zone placée (incluant le fond perdu demandé)
- `--labels` : imprime `p.X` pour vérifier rapidement l'ordre d'imposition
- `inspect` : affiche MediaBox / CropBox / TrimBox / BleedBox + bleed détecté

Exemple “mode test” :

```bash
uv run pdf4up-saddle impose Booky.pdf magazine_A4_impose.pdf --trim-size-mm 125x85 --labels --debug-boxes --marks-style full
```

## Options utiles

- `--bleed-mm 3` : demande 3 mm de fond perdu sur les bords coupés.
- `--spine-bleed-mm 0` : pas de fond perdu au pli central, recommandé en piqure a cheval.
- `--clip-to-bleed-box` : limite le contenu a la BleedBox du PDF source si elle existe.
- `--marks-style minimal` : marques seulement sur les bords externes.
- `--marks-style full` : marques à tous les coins de chaque page.
- `--rotate-back` : tourne les versos de 180 degrés si le test recto-verso sort à l'envers.
- `--pad-multiple 8` : complète automatiquement avec des pages blanches pour remplir des feuilles A4 entières.
- `--pad-multiple 4` : autorise une dernière feuille A4 à moitié vide si le total n'est pas multiple de 8.

## Impression

Imprimez le PDF impose en :

- A4 paysage
- taille reelle / 100 %
- recto-verso
- testez d'abord une feuille avec `--labels`

Si le verso est a l'envers, relancez avec `--rotate-back`, ou changez le retournement bord long / bord court dans le pilote d'impression.
