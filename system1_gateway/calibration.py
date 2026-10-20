"""Temperature calibration, provider-neutral.

System-1 engines ship over-confident (Laya: raw ECE 0.21-0.47). One scalar temperature T per
(provider, model, question or option count) fixes most of it: p_i <- p_i^(1/T) / sum_j p_j^(1/T),
which equals dividing the logits by T. The argmax, and so accuracy, never changes; only how much
the confidence can be trusted does, which is what min_confidence thresholds on.

Entries come from scripts/calibrate.py. Lookup order: the user file (fitted on this machine), then
the file shipped with the package (fitted once, shared by every install). Within a file, an entry
for the exact question wins over one for the option count. An entry whose provider or model
differs from the running one is ignored, so switching checkpoints can't apply a stale fit.
"""

import json
import math
from pathlib import Path

USER_FILE = Path("~/.system1-gateway/calibration.json").expanduser()
SHIPPED_FILE = Path(__file__).with_name("calibration.json")


def load(paths=(USER_FILE, SHIPPED_FILE)) -> list:
    """All entries, user file first. Unreadable files are skipped: calibration is an improvement, not a dependency."""
    entries = []
    for path in paths:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entries += [e for e in data.get("entries", []) if isinstance(e, dict) and _valid_t(e.get("temperature"))]
    return entries


def _valid_t(t) -> bool:
    return isinstance(t, (int, float)) and not isinstance(t, bool) and 0.05 <= t <= 20


def find(entries: list, provider: str, model, question: str, n_options: int):
    """The best matching entry, or None."""
    same = [e for e in entries if e.get("provider") == provider and e.get("model") == model]
    for e in same:
        if e.get("question") == question and e.get("n_options") == n_options:
            return e
    for e in same:
        if e.get("question") is None and e.get("n_options") == n_options:
            return e
    return None


def scale(probs: dict, temperature: float) -> dict:
    """Temperature-scale a probability distribution (keys kept, values renormalised)."""
    eps = 1e-12
    logits = {k: math.log(max(p, eps)) / temperature for k, p in probs.items()}
    top = max(logits.values())
    exp = {k: math.exp(v - top) for k, v in logits.items()}
    total = sum(exp.values())
    return {k: v / total for k, v in exp.items()}
