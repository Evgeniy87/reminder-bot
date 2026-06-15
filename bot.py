import logging
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = "8876477393:AAEuiTfmsO-zTiNeCWuNSrZpmCla8WSjhFw"
TIMEZONE  = ZoneInfo("Europe/Kyiv")
DB_PATH   = "reminders.db"

# Daily morning broadcast. Set to [] to disable.
DAILY_BROADCASTS = [
    {"hour": 9, "minute": 0, "text": "☀️ Гарного ранку! Перевір свої нагадування: /list"},
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ConversationHandler states
ASK_TEXT, ASK_TIME = range(2)


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
        "👋 Привіт! Я твій особистий бот-нагадувач.\n\n"
        "📌 Команди:\n"
        "/remind — додати нагадування\n"
        "/list — переглянути активні\n"
        "/delete <id> — видалити\n"
        "/cancel — скасувати поточну дію"
    )


# ── /remind conversation ──────────────────────────────────────────────────────
async def remind_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Про що нагадати?")
    return ASK_TEXT

async def remind_got_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["remind_text"] = update.message.text.strip()
    await update.message.reply_text(
        "🕐 Коли нагадати?\n\n"
        "Формати:\n"
        "• `14:30` — сьогодні о 14:30\n"
        "• `25.06 14:30` — 25 червня\n"
        "• `25.06.2026 14:30` — конкретна дата",
        parse_mode="Markdown",
    )
    return ASK_TIME

async def remind_got_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    dt_utc = parse_dt(raw)

    if dt_utc is None:
        await update.message.reply_text(
            "❌ Не розумію цей формат. Спробуй ще раз:\n"
            "• `14:30`\n• `25.06 14:30`\n• `25.06.2026 14:30`",
            parse_mode="Markdown",
        )
        return ASK_TIME  # stay in same state, ask again

    now_utc = datetime.now(ZoneInfo("UTC"))
    if dt_utc <= now_utc:
        await update.message.reply_text("❌ Цей час вже минув. Вкажи майбутній час.")
        return ASK_TIME

    text = ctx.user_data.pop("remind_text")
    chat_id = update.effective_chat.id

    with db() as conn:
        conn.execute(
            "INSERT INTO reminders (chat_id, text, remind_at) VALUES (?, ?, ?)",
            (chat_id, text, dt_utc.isoformat()),
        )

    await update.message.reply_text(
        f"✅ Готово!\n\n"
        f"📝 {text}\n"
        f"🕐 {fmt_local(dt_utc.isoformat())}",
    )
    return ConversationHandler.END

async def remind_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Скасовано.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ── /list ─────────────────────────────────────────────────────────────────────
async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    with db() as conn:
        rows = conn.execute(
            "SELECT id, text, remind_at FROM reminders WHERE chat_id=? AND done=0 ORDER BY remind_at",
            (chat_id,),
        ).fetchall()

    if not rows:
        await update.message.reply_text("📭 Активних нагадувань немає.")
        return

    lines = ["📋 *Твої нагадування:*\n"]
    for r in rows:
        lines.append(f"🔔 *#{r['id']}* {fmt_local(r['remind_at'])}\n   {r['text']}")

    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


# ── /delete ───────────────────────────────────────────────────────────────────
async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not ctx.args:
        await update.message.reply_text("Вкажи ID: /delete 3\n\nДивись ID у /list")
        return
    try:
        rid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID має бути числом.")
        return

    with db() as conn:
        cur = conn.execute(
            "DELETE FROM reminders WHERE id=? AND chat_id=?", (rid, chat_id)
        )

    if cur.rowcount:
        await update.message.reply_text(f"🗑 Нагадування #{rid} видалено.")
    else:
        await update.message.reply_text(f"❌ Нагадування #{rid} не знайдено.")


# ── Background: fire due reminders ───────────────────────────────────────────
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


# ── Background: daily broadcast ───────────────────────────────────────────────
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

    conv = ConversationHandler(
        entry_points=[CommandHandler("remind", remind_start)],
        states={
            ASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, remind_got_text)],
            ASK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, remind_got_time)],
        },
        fallbacks=[CommandHandler("cancel", remind_cancel)],
    )

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("list",   cmd_list))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(conv)

    app.job_queue.run_repeating(check_reminders, interval=60, first=5)

    from datetime import time as dtime
    for bc in DAILY_BROADCASTS:
        t = dtime(hour=bc["hour"], minute=bc["minute"], tzinfo=TIMEZONE)
        app.job_queue.run_daily(daily_broadcast, time=t, data=bc["text"])

    log.info("Bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
