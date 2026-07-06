import sys
from pathlib import Path

# merge_mise_tools.py ships as part of the copier template (template/_tasks/)
# and stays there; only its tests live alongside the rest of this repo's own
# test infra.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "template" / "_tasks"))
