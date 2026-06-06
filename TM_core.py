"""
TM_core.py v2.0 — Dynamic Time Warping (DTW)
============================================
Alignement temporel optimal entre deux clips par programmation dynamique.

Algorithme : DTW avec bande de Sakoe-Chiba.
  - Construit une matrice de coût accumulée entre ref et src
  - Trouve le chemin optimal (monotone + continu) par programmation dynamique
  - La bande limite le décalage max autorisé (= fenêtre)

C'est l'algorithme académique de référence pour le "temporal video alignment".
Garantit un remap globalement optimal, sans faux saut ni dérive.
"""
import nuke
import cv2
import numpy as np
import os


def update_status(node, msg):
    """Met à jour le knob status (Text_Knob) de façon sûre."""
    try:
        k = node.knob("status")
        if k is not None:
            k.setValue(str(msg))
        nuke.updateUI()
    except Exception:
        pass


def set_info(node, msg):
    """Met à jour le knob remap_info de façon sûre."""
    try:
        k = node.knob("remap_info")
        if k is not None:
            k.setValue(str(msg))
    except Exception:
        pass


def get_source_file(node):
    visited = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if n is None or id(n) in visited:
            continue
        visited.add(id(n))
        if n.Class() == "Read":
            return n["file"].getValue().replace("/", os.sep)
        for i in range(n.inputs()):
            stack.append(n.input(i))
    return None


def read_frames(filepath, first_nuke, last_nuke, scale):
    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        raise IOError(f"Impossible d'ouvrir : {filepath}")
    total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W       = max(1, int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)  * scale))
    H       = max(1, int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) * scale))
    f_start = max(0, first_nuke - 1)
    f_end   = min(total - 1, last_nuke - 1)
    cap.set(cv2.CAP_PROP_POS_FRAMES, f_start)
    frames = []
    for _ in range(f_end - f_start + 1):
        ret, frame = cap.read()
        if not ret:
            break
        g = cv2.cvtColor(
            cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA),
            cv2.COLOR_BGR2GRAY
        ).astype(np.float32)
        frames.append(g)
    cap.release()
    return frames


# ─────────────────────────────────────────────────────────────
# DYNAMIC TIME WARPING
# ─────────────────────────────────────────────────────────────

def dtw_align(ref, src, band):
    """
    Aligne ref et src par DTW avec bande de Sakoe-Chiba.

    ref, src : listes de frames (np.array float32 gray)
    band     : décalage max autorisé entre i et j (= fenêtre de recherche)

    Retourne remap : pour chaque frame ref[i], l'index src[j] correspondant.
    """
    N, M = len(ref), len(src)
    INF  = float('inf')

    # Matrice de coût accumulée (N+1 x M+1)
    D = np.full((N + 1, M + 1), INF, dtype=np.float64)
    D[0, 0] = 0.0

    # Programmation dynamique — uniquement dans la bande
    for i in range(1, N + 1):
        j_lo = max(1, i - band)
        j_hi = min(M, i + band)
        ref_i = ref[i - 1]
        for j in range(j_lo, j_hi + 1):
            # coût local = différence absolue moyenne
            c = float(np.abs(ref_i - src[j - 1]).mean())
            # 3 mouvements : diagonal, vertical, horizontal
            D[i, j] = c + min(D[i-1, j-1], D[i-1, j], D[i, j-1])

    # Backtracking — retrouve le chemin optimal
    path = []
    i, j = N, M
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        best = min(
            (D[i-1, j-1], i-1, j-1),
            (D[i-1, j],   i-1, j),
            (D[i, j-1],   i,   j-1),
            key=lambda x: x[0]
        )
        _, i, j = best
    path.reverse()

    # Convertit le chemin en remap (un src par ref via médiane)
    ref_to_src = {}
    for ri, si in path:
        ref_to_src.setdefault(ri, []).append(si)

    remap = []
    for k in range(N):
        if k in ref_to_src:
            remap.append(int(np.median(ref_to_src[k])))
        else:
            remap.append(remap[-1] if remap else k)

    return remap


# ─────────────────────────────────────────────────────────────
# APPLICATION TIMEWARP
# ─────────────────────────────────────────────────────────────

def apply_timewarp(node, remap, first_frame):
    tw = node.node("TemporalMatcher_TimeWarp")
    if tw is None:
        nuke.message("[TemporalMatcher] TimeWarp introuvable dans le Gizmo.")
        return False
    lookup = tw["lookup"]
    lookup.setAnimated()
    # Nettoie l'animation existante
    if lookup.isAnimated():
        lookup.clearAnimated()
    lookup.setAnimated()
    for dst_i, src_j in enumerate(remap):
        t = first_frame + dst_i
        lookup.setValueAt(float(first_frame + src_j), t)
    return True


def reset_remap(node):
    tw = node.node("TemporalMatcher_TimeWarp")
    if tw is None:
        return
    tw["lookup"].clearAnimated()
    tw["lookup"].setExpression("frame")
    update_status(node, "Remap réinitialisé (passthrough)")


# ─────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────

def run_analysis(node):
    src_node = node.input(0)
    ref_node = node.input(1)

    if src_node is None or ref_node is None:
        nuke.message(
            "[TemporalMatcher] Connecte les deux inputs :\n"
            "  Input 0 → Clip IA à corriger\n"
            "  Input 1 → Clip référence"
        )
        return

    src_file = get_source_file(src_node)
    ref_file = get_source_file(ref_node)

    if not src_file or not os.path.exists(src_file):
        nuke.message(f"[TemporalMatcher] Source introuvable :\n{src_file}")
        return
    if not ref_file or not os.path.exists(ref_file):
        nuke.message(f"[TemporalMatcher] Référence introuvable :\n{ref_file}")
        return

    first  = int(node["first_frame"].getValue())
    last   = int(node["last_frame"].getValue())
    band   = int(node["search_window"].getValue())
    scale  = float(node["analysis_scale"].getValue())

    update_status(node, "Lecture référence...")
    ref_frames = read_frames(ref_file, first, last, scale)

    update_status(node, "Lecture source IA (pool complet)...")
    cap       = cv2.VideoCapture(src_file)
    total_src = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    src_frames = read_frames(src_file, 1, total_src, scale)

    if not ref_frames or not src_frames:
        nuke.message("[TemporalMatcher] Impossible de lire les frames.")
        return

    N = len(ref_frames)
    M = len(src_frames)
    update_status(node, f"DTW — alignement {N}x{M} frames | bande ±{band}...")

    remap = dtw_align(ref_frames, src_frames, band)

    update_status(node, "Application TimeWarp...")
    if not apply_timewarp(node, remap, first):
        return

    offsets  = [remap[i] - i for i in range(N)]
    remapped = sum(1 for o in offsets if o != 0)
    details  = "\n".join(
        [f"ref {i:04d} -> src {r:04d} ({r-i:+d})"
         for i, r in enumerate(remap) if abs(r-i) > 0][:60]
    ) or "Remap identite"

    set_info(node, details)
    update_status(
        node,
        f"OK — DTW | {N} frames | bande ±{band} | "
        f"offset min={min(offsets):+d} max={max(offsets):+d} | "
        f"remappees={remapped}/{N}"
    )


def register_menu():
    menu = nuke.menu("Nuke")
    tm   = menu.addMenu("TemporalMatcher")
    tm.addCommand(
        "Create TemporalMatcher",
        lambda: nuke.createNode("TemporalMatcher")
    )
    tm.addCommand(
        "About",
        lambda: nuke.message(
            "TemporalMatcher v2.0 — Dynamic Time Warping\n\n"
            "Input 0 : Clip IA a corriger\n"
            "Input 1 : Clip reference\n\n"
            "Algo : DTW (Dynamic Time Warping) avec bande de Sakoe-Chiba.\n"
            "Alignement temporel globalement optimal entre les deux clips.\n"
            "Garantit monotonie + continuite, sans faux saut ni derive.\n\n"
            "Fenetre recherche = largeur de bande = decalage max autorise\n"
            "  8 = decalages courts (recommande, rapide)\n"
            "  15 = decalages moyens\n"
            "  30 = grands decalages (plus lent)"
        )
    )
