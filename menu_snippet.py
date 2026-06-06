# ─────────────────────────────────────────────────────────────
# A coller dans : C:\Users\<USER>\.nuke\menu.py
# (creer le fichier s'il n'existe pas)
# ─────────────────────────────────────────────────────────────
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
