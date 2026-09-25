#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Application and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""

import logging
from typing import Any
import yfinance as yf
import pandas as pd
import psycopg2

from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

INS_TICKER, SAVE_TICKER = range(2)

conn = psycopg2.connect(database="track-etf-bot",
                        host="127.0.0.1",
                        user="postgres",
                        password="postgres",
                        port="5432")

cursor = conn.cursor()

# Define a few command handlers. These usually take the two arguments update and
# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.message.from_user
    logger.info("start(), @%s (%s): %s", user.username, user.id, update.message.text)

    check_user(user.id, user.username)

    await update.message.reply_text("Welcome!")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    user = update.message.from_user
    logger.info("help_command(), @%s (%s): %s", user.username, user.id, update.message.text)

    check_user(user.id, user.username)

    await update.message.reply_text("Help!")

async def insert_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Insert ticker from user."""
    user = update.message.from_user
    logger.info("insert_ticker(), @%s (%s): %s", user.username, user.id, update.message.text)

    await update.message.reply_text(
        "Write the ticker (ex. AAPL, TTWO, VUAA...)"
    )

    return SAVE_TICKER

async def save_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save ticker from user."""
    user = update.message.from_user
    logger.info("save_ticker(), @%s (%s): %s", user.username, user.id, update.message.text)

    user_id = check_user(user.id, user.username)

    # validazione ?

    insert_ticker_db(user_id, update.message.text)

    await update.message.reply_text(
        "Saved!"
    )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    user = update.message.from_user
    logger.info("cancel(), @%s (%s): %s", user.username, user.id, update.message.text)

    await update.message.reply_text(
        "Bye"
    )

    return ConversationHandler.END

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    user = update.message.from_user
    logger.info("echo(), @%s (%s): %s", user.username, user.id, update.message.text)
    
    await update.message.reply_text(update.message.text)

async def job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("job(): cronjob started")

    cursor.execute("SELECT id, uuid_account, username FROM user_account")
    users = cursor.fetchall()
    logger.info("users: %s", list(users))

    for user in list(users):
        logger.info("user: %s", user)

        tickers = get_ticker(int(user[0]))
        logger.info("tickers of %s: %s", user[3], list(tickers))
    
        for ticker in list(tickers[0]):
            dat = yf.Ticker(ticker)
            info = dat.info

            # logger.info(dat.history(period="1mo", interval="1d"))
            value = dat.history(start="2026-07-23", end="2026-07-24", interval="1d", rounding=True)
            firstDayOfTheMonth = value["Close"].iloc[0]
            #logger.info("firstDay: %s", firstDayOfTheMonth)
    
            value = dat.history(start="2026-07-28", end="2026-07-29", interval="1d", rounding=True)
            today = value["Close"].iloc[0]
            #logger.info("today: %s", today)
    
            diff = today - firstDayOfTheMonth
            changes = diff * 100 / firstDayOfTheMonth
            percentageChange = (str(round(changes, 2)))

            output = "%s (%s - %s), currentPrice: %s %s, percentageChange: %s%%" % (
                info["longName"],
                info["symbol"],
                info["fullExchangeName"],
                info["regularMarketPrice"],
                info["currency"],
                percentageChange,
            )

            await context.bot.send_message(chat_id=user[1], text=output)

def check_user(uuid_account, username) -> int:
    cursor.execute("SELECT * FROM user_account WHERE uuid_account = %s", (str(uuid_account),))
    result = cursor.fetchone()

    logger.info("result: %s", result)

    if not result:
        logger.info("username @%s non trovato!", username)
        cursor.execute("INSERT INTO user_account VALUES (DEFAULT, %s, %s, DEFAULT) RETURNING id", (uuid_account, username,))
        result = cursor.fetchone()
        conn.commit();
        logger.info("username @%s inserito!", username)
    else:
        logger.info("username @%s trovato!", username)

    user_id = result[0]
    return user_id

def insert_ticker_db(user_id: int, ticker: str) -> None:
    cursor.execute("INSERT INTO ticker VALUES (DEFAULT, %s, %s)", (ticker, user_id,))
    conn.commit();

def get_ticker(user_id: int) -> tuple[Any]:
    cursor.execute("SELECT ticker FROM ticker WHERE user_account_id = %s", (user_id,))
    result = cursor.fetchall()
    return result  

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token("8971285224:AAG51SkyJOMO_F68v-Xi68m5tr1kgqrF0ws").build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("insert_ticker", insert_ticker)],
        states={
            SAVE_TICKER: [MessageHandler(filters.TEXT, save_ticker)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # cronjob
    application.job_queue.run_repeating(
        job,
        interval=900,
        first=0,
    )

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()