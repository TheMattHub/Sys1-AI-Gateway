"""The routing policy: text-visible features -> Claude model tier. Yours to edit.

Keep it small and readable; scripts/evaluate.py scores it against outcome labels (safety, savings), both with
the engine's answers and with the teacher's feature labels, so a weak rule and a weak engine can be told apart.
"specified" is recorded but unused until outcome data shows it helps.
"""


def tier(answers: dict) -> str | None:
    """answers: feature key -> "yes" | "no" | None (unanswered). None -> no tier."""
    if None in (answers.get("design"), answers.get("review"), answers.get("read_only")):
        return None
    if answers["design"] == "yes" or answers["review"] == "yes":
        return "opus"
    if answers["read_only"] == "yes":
        return "haiku"
    return "sonnet"
