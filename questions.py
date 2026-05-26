"""
questions.py — Loads questions from disk and applies tag/id filters.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

QUESTIONS_FILE = Path("questions.json")


def load_questions(path: Path = QUESTIONS_FILE) -> list[dict]:
    """Load and validate questions from the JSON file."""
    with open(path) as f:
        questions = json.load(f)

    required_keys = {"id", "question", "answer", "tags"}
    valid = []
    for q in questions:
        if required_keys.issubset(q.keys()):
            valid.append(q)
        else:
            logger.warning("Skipping malformed question: %s", q)

    logger.info("Loaded %d valid questions from %s", len(valid), path)
    return valid


def filter_questions(questions: list[dict], request: dict) -> list[dict]:
    """
    Filter questions by tags and/or excluded IDs.

    request = {
        "tags": ["math", "easy"],   # empty list = all tags
        "exclude_ids": [3, 7]       # optional
    }
    """
    tags = request.get("tags") or []
    exclude_ids = set(request.get("exclude_ids") or [])

    def matches(q: dict) -> bool:
        if q["id"] in exclude_ids:
            return False
        if tags:
            return bool(set(q["tags"]) & set(tags))
        return True

    pool = [q for q in questions if matches(q)]
    logger.info(
        "Filter tags=%s exclude=%s → %d/%d questions",
        tags, list(exclude_ids), len(pool), len(questions),
    )
    return pool


def all_tags(questions: list[dict]) -> list[str]:
    """Return a sorted list of all unique tags across all questions."""
    tags: set[str] = set()
    for q in questions:
        tags.update(q["tags"])
    return sorted(tags)
