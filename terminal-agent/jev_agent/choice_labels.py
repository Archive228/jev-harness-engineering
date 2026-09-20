"""Presentation labels adapted from Nous Research's Hermes Agent (MIT).

Copyright (c) 2025 Nous Research.
Source: tools/clarify_tool.py at c1c84ea37f9cfee75a1bf8326b5597959c7ba499.
The full upstream notice and exact source are in vendor/hermes/.

Our adaptation localizes the recommendation marker and recognizes both marker
languages when reading an answer. Keep bare choice values in persisted state;
these helpers decorate display text only, never infer a user's selection.
"""
from typing import List


RECOMMENDED_LABEL = "(Рекомендуется)"
_RECOMMENDATION_LABELS = (RECOMMENDED_LABEL, "(Recommended)")


def strip_recommended(text: str) -> str:
    """Remove a final recommendation marker without changing the answer text."""
    stripped = str(text).strip()
    for label in _RECOMMENDATION_LABELS:
        if stripped.casefold().endswith(label.casefold()):
            return stripped[:-len(label)].strip()
    return stripped


def mark_recommended(choices: List[str]) -> List[str]:
    """Mark the first of multiple choices once; return a fresh display list."""
    result = list(choices)
    first = str(result[0]).strip() if result else ""
    if len(result) < 2 or not first or first != strip_recommended(first):
        return result
    return ["%s %s" % (first, RECOMMENDED_LABEL)] + result[1:]
