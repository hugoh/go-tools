import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# merge_mise_tools.py ships as part of the copier template (template/_tasks/)
# and stays there; only its tests live alongside the rest of this repo's own
# test infra.
sys.path.insert(0, str(ROOT / "template" / "_tasks"))

# migrate_dev_watch.py is invoked directly from the template's own checkout
# via copier's _migrations (see copier.yml), not copied into consumers, so
# it lives at the repo root rather than under template/.
sys.path.insert(0, str(ROOT / "_migrations"))
