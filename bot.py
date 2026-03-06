import logging
import sqlite3
from datetime import datetime, time
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = "8763564657:AAFz--rc2O0LJZZcy7v6c3yCcoUKNLREajY"
ACCESS_PASSWORD = "Passwort"

DB_FILE = "birthdays.db"
TIMEZONE = "Europe/Berlin"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


def db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS birthdays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                name TEXT,
                birthdate TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                birthday_id INTEGER,
                notify_date TEXT,
                notify_type TEXT,
                UNIQUE(birthday_id, notify_date, notify_type)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS authorized_users (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                authorized_at TEXT NOT NULL
            )
            """
        )


def parse_date(d):
    return datetime.strptime(d, "%Y-%m-%d").date()


def safe_birthday_for_year(birthdate, year):
    try:
        return birthdate.replace(year=year)
    except ValueError:
        return birthdate.replace(year=year, day=28)


def days_until(date_str):
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    b = parse_date(date_str)

    next_b = safe_birthday_for_year(b, today.year)

    if next_b < today:
        next_b = safe_birthday_for_year(b, today.year + 1)

    return (next_b - today).days


def is_authorized(user_id):
    with db() as conn:
        row = conn.execute(
            "SELECT 1 FROM authorized_users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row is not None


def authorize_user(user_id, chat_id):
    with db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO authorized_users (user_id, chat_id, authorized_at)
            VALUES (?, ?, ?)
            """,
            (user_id, chat_id, datetime.now(ZoneInfo(TIMEZONE)).isoformat()),
        )


async def require_auth(update: Update):
    if update.message:
        await update.message.reply_text(
            "🔒 Du bist noch nicht freigeschaltet.\n"
            "Bitte sende zuerst das Passwort."
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not update.effective_chat:
        return

    if is_authorized(update.effective_user.id):
        text = (
            "🎂 Geburtstags Bot\n\n"
            "Du bist bereits freigeschaltet.\n\n"
            "Befehle:\n"
            "/add Name YYYY-MM-DD\n"
            "/list\n"
            "/delete ID\n\n"
            "Beispiel:\n"
            "/add Max 1995-05-12"
        )
        await update.message.reply_text(text)
        return

    await update.message.reply_text(
        "👋 Willkommen beim Geburtstags-Bot.\n\n"
        "Bitte sende jetzt das Passwort, um freigeschaltet zu werden."
    )


async def password_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not update.effective_chat:
        return

    if is_authorized(update.effective_user.id):
        return

    user_text = update.message.text.strip()

    if user_text == ACCESS_PASSWORD:
        authorize_user(update.effective_user.id, update.effective_chat.id)
        await update.message.reply_text(
            "✅ Freischaltung erfolgreich.\n\n"
            "Du kannst jetzt folgende Befehle nutzen:\n"
            "/add Name YYYY-MM-DD\n"
            "/list\n"
            "/delete ID"
        )
    else:
        await update.message.reply_text(
            "❌ Falsches Passwort.\n"
            "Bitte versuche es erneut."
        )


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not update.effective_chat:
        return

    if not is_authorized(update.effective_user.id):
        await require_auth(update)
        return

    if len(context.args) < 2:
        await update.message.reply_text("Benutzung: /add Name YYYY-MM-DD")
        return

    name = " ".join(context.args[:-1]).strip()
    date_str = context.args[-1].strip()

    if not name:
        await update.message.reply_text("Bitte einen Namen angeben.")
        return

    try:
        parse_date(date_str)
    except ValueError:
        await update.message.reply_text("Datum Format: YYYY-MM-DD")
        return

    with db() as conn:
        conn.execute(
            "INSERT INTO birthdays (user_id, chat_id, name, birthdate) VALUES (?, ?, ?, ?)",
            (update.effective_user.id, update.effective_chat.id, name, date_str),
        )

    await update.message.reply_text(f"Gespeichert: {name} {date_str}")


async def list_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    if not is_authorized(update.effective_user.id):
        await require_auth(update)
        return

    with db() as conn:
        rows = conn.execute(
            "SELECT id, name, birthdate FROM birthdays WHERE user_id = ? ORDER BY name COLLATE NOCASE",
            (update.effective_user.id,),
        ).fetchall()

    if not rows:
        await update.message.reply_text("Keine Geburtstage gespeichert.")
        return

    msg = "🎂 Deine Geburtstage:\n\n"
    for r in rows:
        d = days_until(r["birthdate"])
        msg += f'{r["id"]}. {r["name"]} - {r["birthdate"]} ({d} Tage)\n'

    await update.message.reply_text(msg)


async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    if not is_authorized(update.effective_user.id):
        await require_auth(update)
        return

    if not context.args:
        await update.message.reply_text("Benutzung: /delete ID")
        return

    try:
        birthday_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Benutzung: /delete ID")
        return

    with db() as conn:
        cur = conn.execute(
            "DELETE FROM birthdays WHERE id = ? AND user_id = ?",
            (birthday_id, update.effective_user.id),
        )

    if cur.rowcount > 0:
        await update.message.reply_text("Gelöscht")
    else:
        await update.message.reply_text("Eintrag nicht gefunden")


def sent_already(birthday_id, notify_date, notify_type):
    with db() as conn:
        r = conn.execute(
            "SELECT 1 FROM sent WHERE birthday_id = ? AND notify_date = ? AND notify_type = ?",
            (birthday_id, notify_date, notify_type),
        ).fetchone()

    return r is not None


def mark_sent(birthday_id, notify_date, notify_type):
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sent (birthday_id, notify_date, notify_type) VALUES (?, ?, ?)",
            (birthday_id, notify_date, notify_type),
        )


async def check_birthdays(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()

    with db() as conn:
        rows = conn.execute(
            "SELECT id, chat_id, name, birthdate FROM birthdays"
        ).fetchall()

    for r in rows:
        d = days_until(r["birthdate"])

        if d == 7:
            t = "7"
            text = f"🎉 {r['name']} hat in 1 Woche Geburtstag"
        elif d == 2:
            t = "2"
            text = f"🎉 {r['name']} hat in 2 Tagen Geburtstag"
        elif d == 0:
            t = "0"
            text = f"🥳 Heute hat {r['name']} Geburtstag!"
        else:
            continue

        if sent_already(r["id"], today, t):
            continue

        try:
            await context.bot.send_message(r["chat_id"], text)
            mark_sent(r["id"], today, t)
        except Exception as exc:
            logger.error("Fehler beim Senden an %s: %s", r["chat_id"], exc)


def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("list", list_birthdays))
    app.add_handler(CommandHandler("delete", delete))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, password_listener)
    )

    app.job_queue.run_daily(
        check_birthdays,
        time=time(hour=9, minute=0, tzinfo=ZoneInfo(TIMEZONE)),
    )

    print("Bot läuft...")
    app.run_polling()


if __name__ == "__main__":
    main()
