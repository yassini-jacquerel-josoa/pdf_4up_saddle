Voici le réglage propre que je te conseille pour finaliser ton flux **InDesign → PDF pages simples → script Python d’imposition A4**.

## 1. Réglage du document dans InDesign

Dans InDesign, ton document doit rester au **format final réel du magazine**, pas au format A4.

Va dans :

**Fichier > Format de document…**

Mets :

```text
Largeur : 125 mm
Hauteur : 85 mm
Pages en vis-à-vis : activé
Orientation : paysage
```

Ensuite, dans **Fond perdu**, mets idéalement :

```text
Haut : 3 mm
Bas : 3 mm
Extérieur : 3 mm
Intérieur : 0 mm
```

Pourquoi **intérieur = 0 mm** ? Parce qu’en piqûre à cheval, le centre est un **pli**, pas une coupe. Le fond perdu doit surtout servir aux bords coupés. Adobe rappelle que le fond perdu fonctionne seulement si les images ou fonds dépassent réellement la limite de page ; sinon le PDF aura une zone de fond perdu vide. ([Adobe Aide][1])

Très important : tes images ou fonds colorés doivent dépasser jusqu’à la ligne rouge du fond perdu dans InDesign. Si une image s’arrête exactement au bord de page, le script ne pourra pas inventer le fond perdu.

---

## 2. Export PDF depuis InDesign

Va dans :

**Fichier > Exporter…**

Choisis :

```text
Format : Adobe PDF (impression)
```

Ensuite dans la fenêtre d’export :

### Onglet Général

Mets :

```text
Paramètre prédéfini Adobe PDF : PDF/X-4 si disponible
Pages : Toutes
Exporter comme : Pages
```

Il faut absolument choisir **Pages**, pas **Planches**. Adobe indique que l’onglet Général permet de choisir si le PDF est exporté en pages simples ou en planches ; pour notre script, il faut des **pages simples**. ([Adobe][2])

Ne fais pas :

```text
Exporter comme : Planches
Imprimer le cahier
2-haut piqûre à cheval
```

Le script s’occupe de l’imposition. InDesign doit seulement fournir les pages normales : 1, 2, 3, 4, 5…

---

### Onglet Compression

Pour un fichier propre impression :

```text
Images couleur : 300 ppp
Images en niveaux de gris : 300 ppp
Images monochromes : 1200 ppp
Compression : ZIP ou JPEG qualité maximale
```

---

### Onglet Repères et fonds perdus

C’est la partie la plus importante.

Active :

```text
Utiliser les paramètres de fond perdu du document
```

Désactive :

```text
Traits de coupe
Repères de fond perdu
Gammes de couleurs
Informations sur la page
Repères de montage
```

Donc : **pas de repères InDesign**.

Pourquoi ? Parce que notre script ajoute les repères de coupe après l’imposition A4. Si tu mets déjà les repères dans le PDF source, ils deviennent une partie de chaque petite page et peuvent être répétés ou mal placés. Adobe précise que les marques et fonds perdus sont gérés dans l’onglet **Marks and Bleeds / Repères et fonds perdus**, mais ici on veut seulement exporter le fond perdu, pas les marques. ([Adobe Aide][3])

Le bon réglage est donc :

```text
Repères d’impression : tout décoché
Fond perdu : Utiliser les paramètres de fond perdu du document coché
```

---

### Onglet Sortie

Pour un test maison, tu peux garder ton profil actuel.

Pour une impression professionnelle, choisis de préférence :

```text
Conversion des couleurs : Convertir vers la destination / conserver les numéros
Destination : profil CMJN demandé par l’imprimeur
```

Si l’imprimeur ne t’a rien demandé, garde PDF/X-4 et évite de convertir au hasard.

---

## 3. Vérification du PDF exporté

Après export, ton PDF source doit avoir :

```text
1 page PDF = 1 page magazine
format fini : 125 x 85 mm
ordre normal : 1, 2, 3, 4, 5...
pas de planches
pas de repères de coupe InDesign
fond perdu inclus
```

Dans ton ancien test, le PDF source contient seulement 4 pages : couverture page 1, contenu page 2, contenu page 3, et page 4 “Le talent au sommet”. 
Donc pour tester une vraie feuille A4 complète avec **8 pages différentes**, il faut exporter un PDF InDesign de **8 pages**, pas seulement 4.

---

## 4. Commandes du script avec `uv`

Dans le dossier du projet :

```bash
uv sync
```

Puis inspecte d’abord ton PDF :

```bash
uv run pdf4up-saddle inspect magazine.pdf --trim-size-mm 125x85
```

Si tout est bon, fais d’abord une version de contrôle :

```bash
uv run pdf4up-saddle impose magazine.pdf magazine_A4_TEST.pdf --trim-size-mm 125x85 --sheet-orientation landscape --bleed-mm 3 --spine-bleed-mm 0 --clip-to-bleed-box --row-gap-mm 8 --marks-style minimal --labels --debug-boxes
```

Cette version sert seulement à vérifier :

```text
ordre des pages
orientation recto-verso
position sur A4
zones de coupe
```

Quand c’est validé, génère le PDF final sans les aides visuelles :

```bash
uv run pdf4up-saddle impose magazine.pdf magazine_A4_PRINT.pdf --trim-size-mm 125x85 --sheet-orientation landscape --bleed-mm 3 --spine-bleed-mm 0 --clip-to-bleed-box --row-gap-mm 8 --marks-style minimal
```

---

## 5. Paramètres à utiliser selon le cas

Pour un vrai magazine de **8 pages, 16 pages, 24 pages**, utilise :

```bash
uv run pdf4up-saddle impose magazine.pdf magazine_A4_PRINT.pdf --trim-size-mm 125x85 --sheet-orientation landscape --bleed-mm 3 --spine-bleed-mm 0 --clip-to-bleed-box --row-gap-mm 8 --marks-style minimal
```

Pour ton **test de 4 pages** avec une seule copie sur la feuille :

```bash
uv run pdf4up-saddle impose test-01.pdf test_4pages.pdf --trim-size-mm 125x85 --sheet-orientation landscape --bleed-mm 3 --spine-bleed-mm 0 --clip-to-bleed-box --row-gap-mm 8 --marks-style minimal
```

Pour ton **test de 4 pages** en remplissant toute la feuille avec deux copies du même mini-livret :

```bash
uv run pdf4up-saddle impose test-01.pdf test_4pages_2copies.pdf --trim-size-mm 125x85 --sheet-orientation landscape --bleed-mm 3 --spine-bleed-mm 0 --clip-to-bleed-box --row-gap-mm 8 --marks-style minimal --fill-sheet-mode repeat-copy
```

Mais attention : `--fill-sheet-mode repeat-copy` est seulement pour produire **deux exemplaires identiques** d’un livret de 4 pages. Pour un vrai magazine de 8 pages différentes, il ne faut pas l’utiliser.

---

## 6. Résultat attendu pour un PDF de 8 pages

Si ton PDF contient 8 pages, le script doit produire :

Recto A4 :

```text
[ 8 ][ 1 ]
[ 6 ][ 3 ]
```

Verso A4 :

```text
[ 2 ][ 7 ]
[ 4 ][ 5 ]
```

C’est le bon principe pour une piqûre à cheval avec coupe ensuite.

---

## 7. Impression finale

Dans Acrobat ou ton lecteur PDF :

```text
Papier : A4
Orientation : paysage
Échelle : taille réelle / 100 %
Recto-verso : activé
Ajuster à la page : désactivé
```

Teste d’abord une seule feuille avec la version `TEST`.

Si le verso sort à l’envers, relance avec :

```bash
uv run pdf4up-saddle impose magazine.pdf magazine_A4_TEST_ROTATE.pdf --trim-size-mm 125x85 --sheet-orientation landscape --bleed-mm 3 --spine-bleed-mm 0 --clip-to-bleed-box --row-gap-mm 8 --marks-style minimal --labels --debug-boxes --rotate-back
```

Puis, si c’est bon :

```bash
uv run pdf4up-saddle impose magazine.pdf magazine_A4_PRINT.pdf --trim-size-mm 125x85 --sheet-orientation landscape --bleed-mm 3 --spine-bleed-mm 0 --clip-to-bleed-box --row-gap-mm 8 --marks-style minimal --rotate-back
```

La règle simple : **InDesign exporte des pages propres avec fond perdu, le script fait l’imposition A4 et les repères de coupe.**

[1]: https://helpx.adobe.com/indesign/using/printers-marks-bleeds.html?utm_source=chatgpt.com "Specify printer’s marks, bleeds, or slug areas in Adobe InDesign"
[2]: https://www.adobe.com/learn/indesign/web/export-settings-pdf-and-print?utm_source=chatgpt.com "Learn InDesign - Make the perfect PDF for your needs - Adobe"
[3]: https://helpx.adobe.com/ph_fil/indesign/how-to/set-print-bleed.html?utm_source=chatgpt.com "How to set a print bleed in InDesign - Adobe Inc."
