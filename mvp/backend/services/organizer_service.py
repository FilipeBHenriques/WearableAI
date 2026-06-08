"""Classifies a transcript into a note category.

Rules are intentionally simple and easy to extend.
When adding an LLM later, replace the body of categorize() only.
"""


def categorize(text: str) -> str:
    t = text.lower()
    if "remind me" in t:
        return "Reminder"
    if "todo" in t or "task" in t:
        return "Task"
    return "Idea"
