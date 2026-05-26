"""
deck.py — Manages the shuffled question deck with persistence.

The deck works like a physical card deck:
- Cards are drawn in shuffled order without repeats.
- Once all cards are drawn, the deck reshuffles automatically.
- State is persisted to disk so restarts don't lose position.
"""

import json
import random
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STATE_FILE = Path("state.json")


class Deck:
    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self.state = self._load()

    # ------------------------------------------------------------------ #
    #  Persistence                                                          #
    # ------------------------------------------------------------------ #

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                logger.info(
                    "State loaded: %d remaining, %d sent",
                    len(data.get("remaining", [])),
                    len(data.get("sent", [])),
                )
                return data
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Corrupt state file, resetting: %s", e)
        return {"remaining": [], "sent": [], "active_filter": {}}

    def _save(self):
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    # ------------------------------------------------------------------ #
    #  Public API                                                           #
    # ------------------------------------------------------------------ #

    def draw(self, pool: list[dict]) -> Optional[dict]:
        """Draw the next question from the pool, reshuffling when exhausted."""
        if not pool:
            logger.warning("draw() called with empty pool")
            return None

        pool_ids = [q["id"] for q in pool]

        # Remaining cards that still belong to the current pool
        remaining = [qid for qid in self.state["remaining"] if qid in pool_ids]

        if not remaining:
            logger.info("Deck exhausted — reshuffling %d cards", len(pool_ids))
            remaining = pool_ids.copy()
            random.shuffle(remaining)
            self.state["sent"] = []

        qid = remaining.pop(0)
        self.state["remaining"] = remaining
        self.state["sent"].append(qid)
        self._save()

        question = next((q for q in pool if q["id"] == qid), None)
        logger.info("Drew question id=%d (%d remaining in deck)", qid, len(remaining))
        return question

    def peek_remaining(self, pool: list[dict]) -> int:
        """How many questions are left before the deck reshuffles."""
        pool_ids = {q["id"] for q in pool}
        return sum(1 for qid in self.state["remaining"] if qid in pool_ids)

    def reset(self, pool: list[dict]):
        """Force a fresh shuffle of the given pool."""
        ids = [q["id"] for q in pool]
        random.shuffle(ids)
        self.state = {"remaining": ids, "sent": [], "active_filter": self.state.get("active_filter", {})}
        self._save()
        logger.info("Deck reset with %d cards", len(ids))

    def save_filter(self, filter_cfg: dict):
        self.state["active_filter"] = filter_cfg
        self._save()

    def load_filter(self) -> dict:
        return self.state.get("active_filter", {})

    @property
    def total_sent(self) -> int:
        return len(self.state.get("sent", []))
