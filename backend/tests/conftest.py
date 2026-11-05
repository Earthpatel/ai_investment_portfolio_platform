import os, sys
from pathlib import Path
os.environ.setdefault("MC_DEV_SYNTHETIC", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
