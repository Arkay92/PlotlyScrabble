"""Allow tests both inside this standalone project and from the parent workspace."""
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
