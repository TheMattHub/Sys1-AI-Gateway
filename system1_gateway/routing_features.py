"""Text-visible features of a task, asked of the System-1 engine in one pass.

A decision model is good at properties you can read off the text (is this a lookup? a review?), not at judging
how hard the work is. So routing asks these, and routing_rule.py turns the answers into a tier (spec 2026-09-30).
"""

MAX_PROMPT_CHARS = 2000  # Laya's typed-decisions checkpoint reads about 1024 tokens
YES_NO = ["yes", "no"]  # asked as a two-option choice: Laya's noul ignores its input
FEATURES = {
    "read_only": "Does the task only ask to look something up, check a status, count something or answer a "
                 "question, without changing any files?",
    "design": "Does the task ask to design, plan, decide between options, research, or define an architecture?",
    "review": "Does the task ask to review or audit existing work?",
    "specified": "Does the task name the exact steps, files or plan item to implement?",
}


def requests_for(text: str, min_confidence: float = 0.0) -> dict:
    """One gateway request per feature. Asked with min_confidence 0 so every answer is recorded; the caller
    applies a threshold. scripts/calibrate.py and scripts/evaluate.py build the same requests."""
    context = {"task": text[:MAX_PROMPT_CHARS]}
    return {key: {"question": q, "options": YES_NO, "context": context, "min_confidence": min_confidence}
            for key, q in FEATURES.items()}


def ask_features(gateway, text: str) -> dict:
    """key -> {"answer": "yes" | "no" | None, "confidence": float | None, "status": str}."""
    results = gateway.decide_many(requests_for(text))
    return {k: {"answer": r["decision"] if r["status"] == "decided" else None,
                "confidence": r["confidence"], "status": r["status"]} for k, r in results.items()}
