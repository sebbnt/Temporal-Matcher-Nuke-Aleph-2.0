# TemporalMatcher v2.0 — Documentation

Plugin Nuke de **réalignement temporel** entre une génération IA et sa plate de référence.
Corrige automatiquement les sautes temporelles (drift, frames en avance/retard) des vidéos
générées par IA (Aleph, Kling, Seedance, Runway, etc.) en les recalant sur la plate source.

---

## 1. Ce que fait le plugin

Quand une IA régénère un plan (changement de décor, de vêtements, ajout d'un élément...),
le mouvement reste globalement identique à la plate d'origine **mais le timing dérive** :
certaines frames arrivent trop tôt, d'autres trop tard, de quelques frames.

Le plugin compare la **génération IA** et la **plate de référence**, calcule pour chaque
frame de la référence quelle frame de la génération IA lui correspond le mieux, et applique
un **remap temporel** (via un TimeWarp interne) qui recale la génération IA sur la plate.

Résultat : la génération IA suit exactement le timing de la plate. En mode différence,
le rendu devient quasi noir (= alignement parfait).

**Important** : le plugin ne génère AUCUNE frame intermédiaire. Il ne fait que **repositionner
des frames existantes** de la génération IA. Aucune interpolation, aucun flou de mouvement ajouté.

---

## 2. L'algorithme : Dynamic Time Warping (DTW)

Le coeur du plugin utilise le **Dynamic Time Warping**, l'algorithme académique de référence
pour l'alignement temporel de deux séquences (utilisé en reconnaissance vocale, biométrie,
analyse de gestes...).

### Principe

1. **Matrice de coût** : on calcule la différence d'image entre chaque frame de la référence
   et chaque frame de la génération IA (dans une bande limitée autour de la diagonale).

2. **Chemin optimal** : par programmation dynamique, DTW trouve le chemin de coût minimal
   à travers cette matrice. Ce chemin associe chaque frame ref à une frame IA.

3. **Trois garanties mathématiques** :
   - *Conditions aux limites* : la 1re frame ref → 1re frame IA, dernière → dernière.
   - *Monotonicité* : le temps ne recule jamais (pas de retour en arrière).
   - *Continuité* : pas de saut brutal, les transitions sont progressives.

C'est ce qui distingue DTW d'un simple "frame matching" : il optimise l'alignement
**globalement** sur toute la séquence, pas frame par frame. Une frame isolée ambiguë
ne crée donc jamais de faux saut, car le chemin global reste cohérent.

### La bande (Sakoe-Chiba)

Pour aller vite et éviter les associations aberrantes, DTW est contraint à une **bande** :
le décalage entre frame ref et frame IA ne peut pas dépasser N frames. C'est le paramètre
"Bande DTW" du node.

---

## 3. Installation

### Prérequis
- **Nuke 13+** (testé sur Nuke 15.0v2, Python 3.10)
- **OpenCV** et **NumPy** dans l'environnement Python de Nuke

### Étape 1 — Copier le dossier

Copier le dossier `TemporalMatcher/` dans le répertoire `.nuke` de l'utilisateur :

```
C:\Users\<USER>\.nuke\TemporalMatcher\
    TemporalMatcher.gizmo
    TM_core.py
    __init__.py
    README.md
```

(Sur Mac/Linux : `~/.nuke/TemporalMatcher/`)

### Étape 2 — Vérifier OpenCV

Dans la Script Editor de Nuke :

```python
import cv2
print(cv2.__version__)
```

- **Une version s'affiche** → passer à l'étape 3.
- **ModuleNotFoundError** → installer OpenCV (voir ci-dessous).

#### Installer OpenCV (si manquant)

Ouvrir un invite de commande Windows **en administrateur** :

```cmd
"C:\Program Files\Nuke15.0v2\python.exe" -m pip install opencv-python-headless numpy
```

(adapter le chemin selon la version de Nuke installée)

Si `python.exe` est introuvable :
```cmd
dir "C:\Program Files\Nuke15.0v2\python*.exe"
```
et adapter le nom. Si pip manque, lancer d'abord :
```cmd
"C:\Program Files\Nuke15.0v2\python.exe" -m ensurepip
```

**Après installation : fermer complètement Nuke et le relancer.**

### Étape 3 — Activer le menu

Ouvrir (ou créer) le fichier `C:\Users\<USER>\.nuke\menu.py` et y coller :

```python
import sys, os
tm_dir = os.path.join(os.path.expanduser("~"), ".nuke", "TemporalMatcher")
nuke.pluginAddPath(tm_dir)
if tm_dir not in sys.path:
    sys.path.insert(0, tm_dir)
try:
    import TM_core
    TM_core.register_menu()
    nuke.tprint("[TemporalMatcher] Charge OK")
except Exception as e:
    nuke.tprint(f"[TemporalMatcher] Erreur : {e}")
```

### Étape 4 — Redémarrer Nuke

Le menu **TemporalMatcher** apparaît dans la barre de menus.
Le node est aussi accessible via `Tab` → taper "TemporalMatcher".

---

## 4. Utilisation

### Branchement

```
   [Read GEN IA]          [Read REF PLATE]
   (.mp4 a corriger)      (.mov reference)
        |                       |
      Input 0               Input 1
        |                       |
        +---[TemporalMatcher]---+
                    |
                 (sortie = GEN IA retimee)
```

- **Input 0 = GEN IA** : la génération IA à corriger (sortie du node = ce clip, retimé)
- **Input 1 = REF PLATE** : la plate de référence (sert uniquement à l'analyse)

> Attention à ne pas inverser les deux entrées. Input 0 est ce qui sort retimé.

### Réglages

| Paramètre | Rôle | Valeur conseillée |
|-----------|------|-------------------|
| **Bande DTW** | Décalage temporel max autorisé (en frames) | 8 (drift court), 15 (moyen), 30 (grand) |
| **Echelle analyse** | Résolution de l'analyse (0.25 = 1/4, plus rapide) | 0.25 |
| **Premiere / Derniere frame** | Plage du plan à traiter | bornes du shot |
| **Plage projet** | Remplit auto la plage depuis le projet Nuke | — |

### Workflow

1. Brancher GEN IA sur Input 0, REF PLATE sur Input 1.
2. Régler la plage de frames (ou cliquer "Plage projet").
3. Régler la Bande DTW selon l'ampleur du décalage (commencer à 8).
4. Cliquer **ANALYSER ET APPLIQUER**.
5. Vérifier le résultat (brancher un Viewer en mode différence sur la sortie + la plate).
6. Si besoin, ajuster la Bande DTW et relancer.

Le bouton **Reset** remet le node en passthrough (aucun remap).

---

## 5. Vérifier le résultat

Pour contrôler l'alignement, comparer la sortie du node avec la plate en **mode différence** :

```
[TemporalMatcher] ---A--- [Merge (difference)] --- [Viewer]
[REF PLATE]       ---B---/
```

- Rendu **quasi noir** = alignement parfait.
- **Halos de contour** = léger décalage résiduel (augmenter un peu la Bande DTW).
- **Image visible en couleur** = mauvais alignement (vérifier que les inputs ne sont pas inversés).

---

## 6. Onglet Debug

L'onglet **Debug** du node affiche le détail du remap calculé :
chaque ligne `ref XXXX -> src YYYY (+/-N)` indique quelle frame source a été
choisie pour chaque frame de la timeline, et l'offset appliqué.

---

## 7. Limites connues

- DTW suppose que les deux clips représentent **le même mouvement**. Si la génération IA
  diverge trop de la plate (mouvement totalement différent), l'alignement n'a pas de sens.
- La bande limite le décalage corrigeable : un drift de 20 frames avec une bande de 8
  ne sera pas entièrement corrigé. Augmenter la bande (au prix de la vitesse).
- L'analyse lit les fichiers source via OpenCV. Les inputs doivent être des **Read nodes**
  pointant vers des fichiers vidéo accessibles sur le disque.

---

## 8. Architecture technique

```
TemporalMatcher/
├── TemporalMatcher.gizmo   # Node Nuke : UI + TimeWarp interne
├── TM_core.py              # Logique : lecture frames, DTW, application TimeWarp
├── __init__.py             # Marqueur de package Python
└── README.md               # Cette documentation
```

- `TemporalMatcher.gizmo` : définit l'interface (knobs), contient un TimeWarp branché
  sur l'Input 0 (GEN IA). Les boutons appellent `TM_core` en forçant un reload du module.
- `TM_core.py` :
  - `read_frames()` — lecture + downscale des frames via OpenCV
  - `dtw_align()` — coeur DTW (matrice de coût + backtracking)
  - `apply_timewarp()` — écrit le remap dans la courbe du TimeWarp
  - `run_analysis()` — orchestration complète déclenchée par le bouton

---

*TemporalMatcher v2.0 — Réalignement temporel par Dynamic Time Warping.*
