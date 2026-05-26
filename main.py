"""
main.py — Entry point. Wires everything together and starts the bot.

Usage:
    python main.py

Configuration is read from config.json. Set your bot token and chat_id there,
or pass them as environment variables TELEGRAM_TOKEN and TELEGRAM_CHAT_ID.
"""

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

from telegram.ext import Application

from bot import FlashcardBot
from deck import Deck
from scheduler import Scheduler

# ------------------------------------------------------------------ #
#  Logging                                                              #
# ------------------------------------------------------------------ #

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log"),
    ],
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#  Config                                                               #
# ------------------------------------------------------------------ #

def load_config() -> dict:
    path = Path("config.json")
    if path.exists():
        with open(path) as f:
            cfg = json.load(f)
    else:
        cfg = {}

    # Environment variables take precedence over config file
    token = os.environ.get("TELEGRAM_TOKEN") or cfg.get("telegram", {}).get("token", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or cfg.get("telegram", {}).get("chat_id", "")

    if not token or token == "YOUR_BOT_TOKEN_HERE":
        logger.error(
            "Telegram bot token not set!\n"
            "  Option 1: Set TELEGRAM_TOKEN environment variable\n"
            "  Option 2: Edit config.json and set telegram.token"
        )
        sys.exit(1)

    if not chat_id or chat_id == "YOUR_CHAT_ID_HERE":
        logger.error(
            "Telegram chat_id not set!\n"
            "  Option 1: Set TELEGRAM_CHAT_ID environment variable\n"
            "  Option 2: Edit config.json and set telegram.chat_id"
        )
        sys.exit(1)

    schedule = cfg.get("schedule", {})
    return {
        "token": token,
        "chat_id": chat_id,
        "min_seconds": int(schedule.get("min_seconds", 3600)),
        "max_seconds": int(schedule.get("max_seconds", 86400)),
    }


# ------------------------------------------------------------------ #
#  Main                                                                 #
# ------------------------------------------------------------------ #

async def main():
    cfg = load_config()
    logger.info("Starting Flashcard Bot...")

    # Build components
    deck = Deck()
    scheduler = Scheduler(
        min_seconds=cfg["min_seconds"],
        max_seconds=cfg["max_seconds"],
    )
    flashcard_bot = FlashcardBot(
        token=cfg["token"],
        chat_id=cfg["chat_id"],
        deck=deck,
        scheduler=scheduler,
    )

    # Build the Telegram application
    app = flashcard_bot.build_app()

    # Run scheduler and Telegram polling concurrently
    async with app:
        await app.initialize()
        await app.start()

        # Start polling in the background
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is polling for updates...")

        # Run the scheduler (this loops forever)
        try:
            await scheduler.run(flashcard_bot)
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled, shutting down...")
        finally:
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
