"""
bot.py — Telegram bot: sends questions and handles user commands.

Commands:
  /next        — Draw and send the next question immediately
  /answer      — Reveal the answer to the last sent question
  /tags        — List all available tags
  /filter      — Show or set the active tag filter
  /status      — Show scheduler status and deck progress
  /reset       — Reshuffle the deck from scratch
  /pause       — Pause the automatic scheduler
  /resume      — Resume the automatic scheduler
  /interval    — Set the random send interval (min and max seconds)
  /help        — Show this help message
"""

import asyncio
import logging
import re
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from deck import Deck
from questions import all_tags, filter_questions, load_questions
from scheduler import Scheduler

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#  Message formatting                                                   #
# ------------------------------------------------------------------ #

def fmt_question(q: dict, index: int, total: int) -> str:
    tags_str = " ".join(f"`{t}`" for t in q["tags"])
    return (
        f"📇 *Question* \\[{index}/{total}\\]\n\n"
        f"*{escape(q['question'])}*\n\n"
        f"Tags: {tags_str}"
    )


def fmt_answer(q: dict) -> str:
    return (
        f"💡 *Answer*\n\n"
        f"||{escape(q['answer'])}||"
    )


def escape(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special)}])", r"\\\1", str(text))


# ------------------------------------------------------------------ #
#  Bot class                                                            #
# ------------------------------------------------------------------ #

class FlashcardBot:
    def __init__(self, token: str, chat_id: str, deck: Deck, scheduler: "Scheduler"):
        self.token = token
        self.chat_id = str(chat_id)
        self.deck = deck
        self.scheduler = scheduler
        self.last_question: Optional[dict] = None
        self.app: Optional[Application] = None

    def build_app(self) -> Application:
        self.app = Application.builder().token(self.token).build()

        handlers = [
            ("next",     self.cmd_next),
            ("answer",   self.cmd_answer),
            ("tags",     self.cmd_tags),
            ("filter",   self.cmd_filter),
            ("status",   self.cmd_status),
            ("reset",    self.cmd_reset),
            ("pause",    self.cmd_pause),
            ("resume",   self.cmd_resume),
            ("interval", self.cmd_interval),
            ("help",     self.cmd_help),
            ("start",    self.cmd_help),
        ]
        for name, handler in handlers:
            self.app.add_handler(CommandHandler(name, handler))

        return self.app

    # ---------------------------------------------------------------- #
    #  Sending helpers                                                   #
    # ---------------------------------------------------------------- #

    async def send_question(self, question: dict):
        """Send a question card to the configured chat."""
        if self.app is None:
            raise RuntimeError("App not built yet")

        pool = self._current_pool()
        remaining = self.deck.peek_remaining(pool)
        total = len(pool)
        sent_in_cycle = total - remaining

        text = fmt_question(question, sent_in_cycle, total)
        await self.app.bot.send_message(
            chat_id=self.chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        self.last_question = question
        logger.info("Sent question id=%d to chat %s", question["id"], self.chat_id)

    async def send_text(self, text: str, update: Update):
        """Reply in the same chat as the command."""
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

    # ---------------------------------------------------------------- #
    #  Commands                                                          #
    # ---------------------------------------------------------------- #

    async def cmd_next(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Draw the next question and send it immediately."""
        pool = self._current_pool()
        if not pool:
            await self.send_text("⚠️ No questions match the current filter\\.", update)
            return

        question = self.deck.draw(pool)
        await self.send_question(question)

        # Reset the scheduler timer so the next auto-send is from now
        self.scheduler.reset_timer()

    async def cmd_answer(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Reveal the answer to the last sent question."""
        if self.last_question is None:
            await self.send_text("❓ No question has been sent yet\\. Use /next to draw one\\.", update)
            return
        text = fmt_answer(self.last_question)
        await self.send_text(text, update)

    async def cmd_tags(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """List all available tags."""
        questions = load_questions()
        tags = all_tags(questions)
        if not tags:
            await self.send_text("No tags found\\.", update)
            return
        tag_list = "\n".join(f"  • `{escape(t)}`" for t in tags)
        await self.send_text(f"🏷️ *Available tags:*\n\n{tag_list}", update)

    async def cmd_filter(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """
        Show or set the active filter.

        Usage:
          /filter                     — show current filter
          /filter math easy           — filter by tags
          /filter all                 — clear filter (all questions)
        """
        args = ctx.args or []

        if not args:
            # Show current filter
            cfg = self.deck.load_filter()
            active_tags = cfg.get("tags") or []
            if active_tags:
                tag_str = ", ".join(f"`{escape(t)}`" for t in active_tags)
                await self.send_text(f"🔍 *Active filter:* {tag_str}", update)
            else:
                await self.send_text("🔍 *Active filter:* all questions", update)
            pool = self._current_pool()
            await self.send_text(f"📦 Matched questions: *{escape(str(len(pool)))}*", update)
            return

        if args[0].lower() == "all":
            new_filter = {"tags": [], "exclude_ids": []}
        else:
            new_filter = {"tags": args, "exclude_ids": []}

        # Validate that new filter returns at least one question
        questions = load_questions()
        pool = filter_questions(questions, new_filter)
        if not pool:
            await self.send_text(
                f"⚠️ No questions match tags: {', '.join(f'`{escape(t)}`' for t in args)}\\. Filter not changed\\.",
                update,
            )
            return

        self.deck.save_filter(new_filter)
        self.deck.reset(pool)  # Fresh shuffle for new filter

        tag_str = ", ".join(f"`{escape(t)}`" for t in new_filter["tags"]) or "all"
        await self.send_text(
            f"✅ Filter set to: *{tag_str}*\n📦 {escape(str(len(pool)))} questions in deck\\.",
            update,
        )

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Show scheduler and deck status."""
        pool = self._current_pool()
        remaining = self.deck.peek_remaining(pool)
        total = len(pool)
        sent = total - remaining

        paused = self.scheduler.paused
        min_s, max_s = self.scheduler.min_seconds, self.scheduler.max_seconds
        next_in = self.scheduler.seconds_until_next()

        status_icon = "⏸️" if paused else "▶️"
        next_str = f"{next_in}s" if next_in is not None else "N/A"

        cfg = self.deck.load_filter()
        active_tags = cfg.get("tags") or []
        filter_str = ", ".join(f"`{escape(t)}`" for t in active_tags) or "all"

        text = (
            f"{status_icon} *Scheduler:* {'paused' if paused else 'running'}\n"
            f"⏱️ *Interval:* {escape(str(min_s))}s – {escape(str(max_s))}s\n"
            f"⏳ *Next send in:* {escape(next_str)}\n\n"
            f"📇 *Deck progress:* {escape(str(sent))}/{escape(str(total))} sent this cycle\n"
            f"🔍 *Filter:* {filter_str}"
        )
        await self.send_text(text, update)

    async def cmd_reset(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Reshuffle the deck from the beginning."""
        pool = self._current_pool()
        self.deck.reset(pool)
        self.scheduler.reset_timer()
        await self.send_text(
            f"🔀 Deck reshuffled\\! {escape(str(len(pool)))} cards ready\\.", update
        )

    async def cmd_pause(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Pause automatic question sending."""
        if self.scheduler.paused:
            await self.send_text("⏸️ Scheduler is already paused\\.", update)
            return
        self.scheduler.pause()
        await self.send_text("⏸️ Scheduler paused\\. Use /resume to restart\\.", update)

    async def cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Resume automatic question sending."""
        if not self.scheduler.paused:
            await self.send_text("▶️ Scheduler is already running\\.", update)
            return
        self.scheduler.resume()
        await self.send_text("▶️ Scheduler resumed\\.", update)

    async def cmd_interval(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """
        Set the random sending interval.

        Usage:
          /interval                   — show current interval
          /interval 1800 7200         — set min=1800s max=7200s
          /interval 30m 2h            — also accepts m/h suffixes
        """
        args = ctx.args or []

        if not args:
            min_s, max_s = self.scheduler.min_seconds, self.scheduler.max_seconds
            await self.send_text(
                f"⏱️ *Current interval:* {escape(fmt_duration(min_s))} – {escape(fmt_duration(max_s))}",
                update,
            )
            return

        if len(args) != 2:
            await self.send_text(
                "Usage: `/interval <min> <max>`\nExample: `/interval 1800 7200` or `/interval 30m 2h`",
                update,
            )
            return

        try:
            min_s = parse_duration(args[0])
            max_s = parse_duration(args[1])
        except ValueError as e:
            await self.send_text(f"⚠️ Invalid duration: {escape(str(e))}", update)
            return

        if min_s <= 0 or max_s <= 0:
            await self.send_text("⚠️ Durations must be positive\\.", update)
            return
        if min_s > max_s:
            await self.send_text("⚠️ Minimum must be ≤ maximum\\.", update)
            return

        self.scheduler.set_interval(min_s, max_s)
        await self.send_text(
            f"✅ Interval updated: {escape(fmt_duration(min_s))} – {escape(fmt_duration(max_s))}",
            update,
        )

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Show help text."""
        text = (
            "🤖 *Flashcard Bot — Commands*\n\n"
            "/next — Draw the next question now\n"
            "/answer — Reveal the last answer \\(spoiler\\)\n"
            "/tags — List all available tags\n"
            "/filter \\[tags…\\] — Set or view tag filter\n"
            "/status — Scheduler and deck info\n"
            "/reset — Reshuffle the deck\n"
            "/pause — Pause auto\\-sending\n"
            "/resume — Resume auto\\-sending\n"
            "/interval \\[min max\\] — View or set send interval\n"
            "/help — Show this message\n\n"
            "_Answers are hidden as spoilers — tap to reveal\\._"
        )
        await self.send_text(text, update)

    # ---------------------------------------------------------------- #
    #  Helpers                                                           #
    # ---------------------------------------------------------------- #

    def _current_pool(self) -> list[dict]:
        questions = load_questions()
        cfg = self.deck.load_filter()
        return filter_questions(questions, cfg)


# ------------------------------------------------------------------ #
#  Duration utilities                                                   #
# ------------------------------------------------------------------ #

def parse_duration(s: str) -> int:
    """Parse '30m', '2h', '3600' into seconds."""
    s = s.strip().lower()
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    if s.endswith("m"):
        return int(s[:-1]) * 60
    return int(s)


def fmt_duration(seconds: int) -> str:
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"
