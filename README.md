# 📇 Flashcard Bot

A Telegram bot that sends Q&A flashcards at random intervals,
drawing from a shuffled deck that never repeats until all cards
have been seen.

Made with Claude Sonnet 4.6
---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create your bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the **token** you receive

### 3. Get your chat ID

1. Message your bot once (e.g. `/start`)
2. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find `"chat": {"id": ...}` — that's your chat ID

### 4. Configure

**Option A — Edit `config.json`:**
```json
{
  "telegram": {
    "token": "123456:ABC-your-token-here",
    "chat_id": "987654321"
  },
  "schedule": {
    "min_seconds": 3600,
    "max_seconds": 86400
  }
}
```

**Option B — Environment variables:**
```bash
export TELEGRAM_TOKEN="123456:ABC-your-token-here"
export TELEGRAM_CHAT_ID="987654321"
```

### 5. Add your questions

Edit `questions.json`:
```json
[
  {
    "id": 1,
    "question": "What is X?",
    "answer": "Y.",
    "tags": ["topic", "difficulty"]
  }
]
```

Rules:
- `id` must be unique across all questions
- `tags` is a list of strings (used for filtering)
- All four fields are required

### 6. Run

```bash
python main.py
```

---

## Commands

| Command | Description |
|---|---|
| `/next` | Draw and send the next question immediately |
| `/answer` | Reveal the answer to the last question (spoiler) |
| `/tags` | List all available tags |
| `/filter [tags…]` | Set or view the active tag filter |
| `/filter all` | Clear the filter (all questions) |
| `/status` | Show scheduler state and deck progress |
| `/reset` | Reshuffle the deck from scratch |
| `/pause` | Pause automatic sending |
| `/resume` | Resume automatic sending |
| `/interval [min max]` | View or set the send interval |
| `/help` | Show command list |

### Interval examples

```
/interval 1800 7200       # 30 min to 2 hours
/interval 30m 2h          # same with unit suffixes
/interval 3600 86400      # 1 hour to 24 hours (default)
```

---

## How the deck works

- Questions are drawn in a **random shuffled order** — no repeats.
- When the last card is drawn, the deck **automatically reshuffles**.
- State is saved to `state.json` so restarts don't lose your position.
- Changing the filter via `/filter` resets and reshuffles the deck.

---

## File structure

```
flashcard_bot/
├── main.py           # Entry point
├── bot.py            # Telegram commands and message formatting
├── scheduler.py      # Random-interval async scheduler
├── deck.py           # Shuffle-deck logic with persistence
├── questions.py      # Load and filter questions
├── questions.json    # Your Q&A content
├── config.json       # Token, chat_id, default interval
├── state.json        # Auto-generated: deck position
├── bot.log           # Auto-generated: log file
└── requirements.txt
```

---

## Running as a service (Linux)

Create `/etc/systemd/system/flashcard-bot.service`:

```ini
[Unit]
Description=Flashcard Telegram Bot
After=network.target

[Service]
WorkingDirectory=/path/to/flashcard_bot
ExecStart=/usr/bin/python3 main.py
Restart=on-failure
RestartSec=10
Environment=TELEGRAM_TOKEN=your_token
Environment=TELEGRAM_CHAT_ID=your_chat_id

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable flashcard-bot
sudo systemctl start flashcard-bot
sudo systemctl status flashcard-bot
```
