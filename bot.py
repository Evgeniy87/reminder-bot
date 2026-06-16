import logging
import sqlite3
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8876477393:AAEuiTfmsO-zTiNeCWuNSrZpmCla8WSjhFw")
TIMEZONE  = ZoneInfo("Europe/Kyiv")
DB_PATH   = "reminders.db"

DAILY_BROADCASTS = [
    {"hour": 9, "minute": 0, "text": "☀️ Гарного ранку! Перевір свої нагадування 👇"},
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ConversationHandler states
ASK_TEXT, ASK_TIME = range(2)

# ── Keyboards ─────────────────────────────────────────────────────────────────
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔔 Нове нагадування")],
        [KeyboardButton("📋 Мої нагадування"), KeyboardButton("🗑 Видалити")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("❌ Скасувати")]],
    resize_keyboard=True,
)


# ── Database ──────────────────────────────────────────────────────────────────
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   INTEGER NOT NULL,
                text      TEXT    NOT NULL,
                remind_at TEXT    NOT NULL,
                done      INTEGER DEFAULT 0
            )
        """)


# ── Time parsing ──────────────────────────────────────────────────────────────
FORMATS = ["%d.%m.%Y %H:%M", "%d.%m %H:%M", "%H:%M"]

def parse_dt(raw: str):
    now = datetime.now(TIMEZONE)
    for fmt in FORMATS:
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            if fmt == "%H:%M":
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
            elif fmt == "%d.%m %H:%M":
                dt = dt.replace(year=now.year)
            return dt.replace(tzinfo=TIMEZONE).astimezone(ZoneInfo("UTC"))
        except ValueError:
            continue
    return None

def fmt_local(iso: str) -> str:
    dt = datetime.fromisoformat(iso).replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(TIMEZONE).strftime("%d.%m.%Y %H:%M")


# ── /start ────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт! Я твій особистий бот-нагадувач.\nОбери дію 👇",
        reply_markup=MAIN_KEYBOARD,
    )


# ── New reminder conversation ─────────────────────────────────────────────────
async def remind_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Про що нагадати?",
        reply_markup=CANCEL_KEYBOARD,
    )
    return ASK_TEXT

async def remind_got_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["remind_text"] = update.message.text.strip()
    await update.message.reply_text(
        "🕐 Коли нагадати?\n\n"
        "Формати:\n"
        "• `14:30` — сьогодні\n"
        "• `25.06 14:30`\n"
        "• `25.06.2026 14:30`",
        parse_mode="Markdown",
        reply_markup=CANCEL_KEYBOARD,
    )
    return ASK_TIME

async def remind_got_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    dt_utc = parse_dt(raw)

    if dt_utc is None:
        await update.message.reply_text(
            "❌ Не розумію формат. Спробуй ще раз:\n"
            "• `14:30`\n• `25.06 14:30`\n• `25.06.2026 14:30`",
            parse_mode="Markdown",
            reply_markup=CANCEL_KEYBOARD,
        )
        return ASK_TIME

    if dt_utc <= datetime.now(ZoneInfo("UTC")):
        await update.message.reply_text(
            "❌ Цей час вже минув. Вкажи майбутній час.",
            reply_markup=CANCEL_KEYBOARD,
        )
        return ASK_TIME

    text = ctx.user_data.pop("remind_text")
    with db() as conn:
        conn.execute(
            "INSERT INTO reminders (chat_id, text, remind_at) VALUES (?, ?, ?)",
            (update.effective_chat.id, text, dt_utc.isoformat()),
        )

    await update.message.reply_text(
        f"✅ Нагадування встановлено!\n\n"
        f"📝 {text}\n"
        f"🕐 {fmt_local(dt_utc.isoformat())}",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END

async def remind_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Скасовано.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── List reminders ────────────────────────────────────────────────────────────
async def show_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    with db() as conn:
        rows = conn.execute(
            "SELECT id, text, remind_at FROM reminders WHERE chat_id=? AND done=0 ORDER BY remind_at",
            (chat_id,),
        ).fetchall()

    if not rows:
        await update.message.reply_text(
            "📭 Активних нагадувань немає.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    lines = ["📋 *Твої нагадування:*\n"]
    for r in rows:
        lines.append(f"🔔 *#{r['id']}* — {fmt_local(r['remind_at'])}\n   {r['text']}")

    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


# ── Delete conversation ───────────────────────────────────────────────────────
ASK_DELETE_ID = 2

async def delete_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    with db() as conn:
        rows = conn.execute(
            "SELECT id, text, remind_at FROM reminders WHERE chat_id=? AND done=0 ORDER BY remind_at",
            (chat_id,),
        ).fetchall()

    if not rows:
        await update.message.reply_text(
            "📭 Нема чого видаляти.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    # Build a keyboard with one button per reminder
    buttons = [
        [KeyboardButton(f"#{r['id']} — {fmt_local(r['remind_at'])} — {r['text'][:30]}")]
        for r in rows
    ]
    buttons.append([KeyboardButton("❌ Скасувати")])

    await update.message.reply_text(
        "🗑 Яке нагадування видалити?",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True),
    )
    return ASK_DELETE_ID

async def delete_got_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    try:
        rid = int(text.split("—")[0].replace("#", "").strip())
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Не вдалося визначити ID. Спробуй ще раз.",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    with db() as conn:
        cur = conn.execute(
            "DELETE FROM reminders WHERE id=? AND chat_id=?", (rid, chat_id)
        )

    if cur.rowcount:
        await update.message.reply_text(f"🗑 Нагадування #{rid} видалено.", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text(f"❌ Нагадування #{rid} не знайдено.", reply_markup=MAIN_KEYBOARD)

    return ConversationHandler.END


# ── Background jobs ───────────────────────────────────────────────────────────
async def check_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    now_utc = datetime.now(ZoneInfo("UTC"))
    with db() as conn:
        rows = conn.execute(
            "SELECT id, chat_id, text FROM reminders WHERE done=0 AND remind_at <= ?",
            (now_utc.isoformat(),),
        ).fetchall()
        for r in rows:
            try:
                await ctx.bot.send_message(
                    chat_id=r["chat_id"],
                    text=f"🔔 *Нагадування!*\n\n{r['text']}",
                    parse_mode="Markdown",
                )
            except Exception as e:
                log.warning("Failed to send reminder %d: %s", r["id"], e)
            conn.execute("UPDATE reminders SET done=1 WHERE id=?", (r["id"],))

async def daily_broadcast(ctx: ContextTypes.DEFAULT_TYPE):
    text = ctx.job.data
    with db() as conn:
        chat_ids = {r[0] for r in conn.execute("SELECT DISTINCT chat_id FROM reminders").fetchall()}
    for cid in chat_ids:
        try:
            await ctx.bot.send_message(chat_id=cid, text=text)
        except Exception as e:
            log.warning("Broadcast failed for %d: %s", cid, e)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    remind_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔔 Нове нагадування$"), remind_start)],
        states={
            ASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, remind_got_text)],
            ASK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, remind_got_time)],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Скасувати$"), remind_cancel),
            CommandHandler("cancel", remind_cancel),
        ],
    )

    delete_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🗑 Видалити$"), delete_start)],
        states={
            ASK_DELETE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_got_id)],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Скасувати$"), remind_cancel),
            CommandHandler("cancel", remind_cancel),
        ],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.Regex("^📋 Мої нагадування$"), show_list))
    app.add_handler(remind_conv)
    app.add_handler(delete_conv)

    app.job_queue.run_repeating(check_reminders, interval=60, first=5)

    from datetime import time as dtime
    for bc in DAILY_BROADCASTS:
        t = dtime(hour=bc["hour"], minute=bc["minute"], tzinfo=TIMEZONE)
        app.job_queue.run_daily(daily_broadcast, time=t, data=bc["text"])

    log.info("Bot started.")
    app.run_polling()

if __name__ == "__main__":
    main()
