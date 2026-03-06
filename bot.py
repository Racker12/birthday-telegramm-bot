import os
import sqlite3
from datetime import datetime, date
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("8763564657:AAFz--rc2O0LJZZcy7v6c3yCcoUKNLREajY")

conn = sqlite3.connect("birthdays.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS birthdays (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
date TEXT
)
""")
conn.commit()


def days_until(birthday):
    today = date.today()
    bday = datetime.strptime(birthday, "%Y-%m-%d").date()

    next_bday = bday.replace(year=today.year)
    if next_bday < today:
        next_bday = next_bday.replace(year=today.year + 1)

    return (next_bday - today).days


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Geburtstags Bot gestartet 🎉")


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = context.args[0]
    birthday = context.args[1]

    cursor.execute(
        "INSERT INTO birthdays (name, date) VALUES (?,?)",
        (name, birthday)
    )
    conn.commit()

    await update.message.reply_text("Geburtstag gespeichert")


async def list_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cursor.execute("SELECT * FROM birthdays")
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("Keine Geburtstage gespeichert")
        return

    text = ""

    for row in rows:
        text += f"{row[0]} - {row[1]} ({row[2]})\n"

    await update.message.reply_text(text)


async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):

    id = context.args[0]

    cursor.execute("DELETE FROM birthdays WHERE id=?", (id,))
    conn.commit()

    await update.message.reply_text("Gelöscht")


async def check_birthdays(context: ContextTypes.DEFAULT_TYPE):

    cursor.execute("SELECT * FROM birthdays")
    rows = cursor.fetchall()

    for row in rows:

        days = days_until(row[2])

        if days == 7:
            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text=f"{row[1]} hat in 7 Tagen Geburtstag"
            )

        if days == 2:
            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text=f"{row[1]} hat in 2 Tagen Geburtstag"
            )

        if days == 0:
            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text=f"Heute hat {row[1]} Geburtstag 🎉"
            )


def main():

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("list", list_birthdays))
    app.add_handler(CommandHandler("delete", delete))

    job_queue = app.job_queue
    job_queue.run_repeating(check_birthdays, interval=86400, first=10)

    app.run_polling()


main()
