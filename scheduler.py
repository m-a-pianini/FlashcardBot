"""
scheduler.py — Async scheduler that sends questions at random intervals.

The scheduler runs as a background asyncio task alongside the Telegram
polling loop. It supports pause/resume and dynamic interval changes.
"""

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bot import FlashcardBot

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, min_seconds: int = 3600, max_seconds: int = 86400):
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds
        self.paused = False
        self._task: Optional[asyncio.Task] = None
        self._next_send_at: Optional[float] = None  # Unix timestamp
        self._reset_event = asyncio.Event()
        self._resume_event = asyncio.Event()
        self._resume_event.set()  # Not paused by default

    # ---------------------------------------------------------------- #
    #  Control                                                           #
    # ---------------------------------------------------------------- #

    def pause(self):
        self.paused = True
        self._resume_event.clear()
        logger.info("Scheduler paused")

    def resume(self):
        self.paused = False
        self._resume_event.set()
        logger.info("Scheduler resumed")

    def reset_timer(self):
        """Restart the countdown from now (e.g. after a manual /next)."""
        self._reset_event.set()
        logger.info("Scheduler timer reset")

    def set_interval(self, min_seconds: int, max_seconds: int):
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds
        self.reset_timer()
        logger.info("Interval updated: %ds–%ds", min_seconds, max_seconds)

    def seconds_until_next(self) -> Optional[int]:
        if self._next_send_at is None or self.paused:
            return None
        remaining = self._next_send_at - time.monotonic()
        return max(0, int(remaining))

    # ---------------------------------------------------------------- #
    #  Main loop                                                         #
    # ---------------------------------------------------------------- #

    async def run(self, bot: "FlashcardBot"):
        """
        Continuously draw and send questions at random intervals.
        Runs as a long-lived asyncio task.
        """
        logger.info("Scheduler started (interval: %ds–%ds)", self.min_seconds, self.max_seconds)

        while True:
            # Wait until unpaused
            await self._resume_event.wait()

            # Pick a random delay
            delay = random.randint(self.min_seconds, self.max_seconds)
            self._next_send_at = time.monotonic() + delay
            logger.info("Next question in %ds (%.1f min)", delay, delay / 60)

            # Sleep with reset support
            self._reset_event.clear()
            try:
                await asyncio.wait_for(self._wait_for_reset(delay), timeout=delay)
                logger.info("Timer reset — picking new delay")
                continue  # Loop and pick a new delay
            except asyncio.TimeoutError:
                pass  # Normal expiry — send the question

            # Check again in case we were paused during the sleep
            if self.paused:
                continue

            # Draw and send
            pool = bot._current_pool()
            if not pool:
                logger.warning("No questions in pool, skipping send")
                continue

            question = bot.deck.draw(pool)
            if question:
                try:
                    await bot.send_question(question)
                except Exception as e:
                    logger.error("Failed to send question: %s", e)

    async def _wait_for_reset(self, timeout: float):
        """Await the reset event; raise TimeoutError if it doesn't fire."""
        await asyncio.wait_for(self._reset_event.wait(), timeout=timeout)
