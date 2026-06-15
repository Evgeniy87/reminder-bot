# 🔔 Telegram Reminder Bot

A personal reminder bot with custom reminders and daily scheduled broadcasts.

## Features
- `/remind` — set a one-time reminder at any date/time
- `/list` — view all active reminders
- `/delete <id>` — delete a reminder
- Daily morning broadcast to all active users (configurable)
- SQLite storage — no external DB needed
- Timezone-aware (Europe/Kyiv by default)

## Setup

### 1. Get a Bot Token
1. Open Telegram → search **@BotFather**
2. Send `/newbot`, follow the steps
3. Copy your token

### 2. Configure the bot
Open `bot.py` and set:
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TIMEZONE   = ZoneInfo("Europe/Kyiv")  # change if needed
```

Optionally edit daily broadcasts:
```python
DAILY_BROADCASTS = [
    {"hour": 9, "minute": 0, "text": "☀️ Гарного ранку! ..."},
]
```
Set to `[]` to disable.

### 3. Run (Windows)
```
run.bat
```
Or manually:
```
pip install -r requirements.txt
python bot.py
```

## Commands

| Command | Description |
|---|---|
| `/start` | Welcome message + help |
| `/remind 14:30 \| Buy groceries` | Reminder today at 14:30 |
| `/remind 25.06 09:00 \| Call doctor` | Reminder on June 25 |
| `/remind 25.06.2026 18:00 \| Meeting` | Full date |
| `/list` | Show active reminders |
| `/delete 3` | Delete reminder #3 |

## Time Formats
- `14:30` — today at 14:30
- `25.06 14:30` — June 25 at 14:30
- `25.06.2026 14:30` — full date

All times are in the configured timezone (Europe/Kyiv).
