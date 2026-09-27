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

import socket
import logging
import yfinance as yf
import psycopg2
import os

from typing import Any
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from datetime import datetime

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

INS_TICKER, SAVE_TICKER = range(2)

load_dotenv()

DB_NAME = os.getenv('DB_NAME')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_PORT = os.getenv('DB_PORT')
BOT_TOKEN = os.getenv('BOT_TOKEN')

PORT = os.getenv('PORT')

conn = psycopg2.connect(database=DB_NAME,
                        host=DB_HOST,
                        user=DB_USER,
                        password=DB_PASSWORD,
                        port=DB_PORT)

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
        logger.info("tickers of %s: %s", user[2], list(tickers))
    
        for ticker in list(tickers):
            logger.info("ticker %s", ticker)
            dat = yf.Ticker(ticker[0])
            info = dat.info

            # logger.info(dat.history(period="1mo", interval="1d"))
            value = dat.history(start=datetime.today().replace(day=1), end=datetime.today().replace(day=2), interval="1d", rounding=True)
            firstDayOfTheMonth = value["Close"].iloc[0]
            logger.info("firstDay: %s", firstDayOfTheMonth)

            # value = dat.history(start=datetime.today(), end=datetime.today() - timedelta(days=1), interval="1d", rounding=True)
            value = dat.history()
            today = value["Close"].iloc[-1]
            logger.info("today: %s", today)
    
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

def create_socket(host='localhost', port=443):
    """
    This function creates a socket that listens to a specific port.
    
    Parameters:
    host (str): The host where the server is running. Default is localhost.
    port (int): The port number to listen to. Default is 12345.
    
    Returns:
    None
    """
    # Create a socket object
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Bind the socket to the host and port
    s.bind((host, port))

    # Listen to the port
    s.listen(5)
    logger.info(f"Socket is listening on {host}:{port}")

    while True:
        # Establish connection with client
        c, addr = s.accept()
        logger.info(f"Got connection from {addr}")

        # Send a thank you message to the client
        c.send(b'Thank you for connecting')

        # Close the connection
        c.close()

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

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
        interval=14400,
        first=0,
    )

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    # Call the function to create a socket and listen to a port
    create_socket()

if __name__ == "__main__":
    main()