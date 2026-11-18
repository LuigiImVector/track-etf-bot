
#!/usr/bin/env python
# pylint: disable=unused-argument

"""
Telegram Bot - Stock Tracker
"""

import asyncio
import os
import threading
import logging

import yfinance as yf
import psycopg2

from contextlib import contextmanager
from aiohttp import web
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from datetime import datetime


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

INS_TICKER, SAVE_TICKER = range(2)

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT")

BOT_TOKEN = os.getenv("BOT_TOKEN")


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

@contextmanager
def db_cursor():

    connection = psycopg2.connect(
        database=DB_NAME,
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )

    try:
        with connection:
            with connection.cursor() as cursor:
                yield cursor

    finally:
        connection.close()


# --------------------------------------------------
# TELEGRAM HANDLERS
# --------------------------------------------------

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    user = update.message.from_user

    logger.info(
        "start(), @%s (%s): %s",
        user.username,
        user.id,
        update.message.text
    )

    check_user(user.id, user.username)

    await update.message.reply_text("Welcome!")


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    user = update.message.from_user

    logger.info(
        "help_command(), @%s (%s): %s",
        user.username,
        user.id,
        update.message.text
    )

    check_user(user.id, user.username)

    await update.message.reply_text("Help!")


async def insert_ticker(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:

    user = update.message.from_user

    logger.info(
        "insert_ticker(), @%s (%s): %s",
        user.username,
        user.id,
        update.message.text
    )

    await update.message.reply_text(
        "Write the ticker (ex. AAPL, TTWO, VUAA...)"
    )

    return SAVE_TICKER


async def save_ticker(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:

    user = update.message.from_user

    logger.info(
        "save_ticker(), @%s (%s): %s",
        user.username,
        user.id,
        update.message.text
    )

    user_id = check_user(user.id, user.username)

    ticker = update.message.text.strip().upper()

    if not ticker:
        await update.message.reply_text("Invalid ticker!")
        return SAVE_TICKER

    try:

        insert_ticker_db(user_id, ticker)

        await update.message.reply_text("Saved!")

    except Exception:

        logger.exception("Error saving ticker")

        await update.message.reply_text(
            "Error saving ticker. Please try again."
        )

    return ConversationHandler.END


async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:

    user = update.message.from_user

    logger.info(
        "cancel(), @%s (%s): %s",
        user.username,
        user.id,
        update.message.text
    )

    await update.message.reply_text("Bye")

    return ConversationHandler.END


async def echo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    user = update.message.from_user

    logger.info(
        "echo(), @%s (%s): %s",
        user.username,
        user.id,
        update.message.text
    )

    await update.message.reply_text(update.message.text)


# --------------------------------------------------
# DATABASE FUNCTIONS
# --------------------------------------------------

def check_user(uuid_account, username) -> int:

    with db_cursor() as cursor:

        cursor.execute(
            """
            SELECT id
            FROM user_account
            WHERE uuid_account = %s
            """,
            (str(uuid_account),)
        )

        result = cursor.fetchone()

        logger.info("result: %s", result)

        if not result:

            logger.info(
                "username @%s non trovato!",
                username
            )

            cursor.execute(
                """
                INSERT INTO user_account
                VALUES (DEFAULT, %s, %s, DEFAULT)
                RETURNING id
                """,
                (uuid_account, username)
            )

            result = cursor.fetchone()

            logger.info(
                "username @%s inserito!",
                username
            )

        else:

            logger.info(
                "username @%s trovato!",
                username
            )

        user_id = result[0]

    return user_id


def insert_ticker_db(
    user_id: int,
    ticker: str
) -> None:

    with db_cursor() as cursor:

        cursor.execute(
            """
            INSERT INTO ticker
            VALUES (DEFAULT, %s, %s)
            """,
            (ticker.upper().strip(), user_id)
        )


def get_ticker(user_id: int) -> list:

    with db_cursor() as cursor:

        cursor.execute(
            """
            SELECT ticker
            FROM ticker
            WHERE user_account_id = %s
            """,
            (user_id,)
        )

        result = cursor.fetchall()

    return result


# --------------------------------------------------
# CRONJOB
# --------------------------------------------------

async def job(
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    logger.info("job(): cronjob started")

    # Retrieve users from database
    with db_cursor() as cursor:

        cursor.execute(
            """
            SELECT id, uuid_account, username
            FROM user_account
            """
        )

        users = cursor.fetchall()

    logger.info("users: %s", users)

    for user in users:

        logger.info("user: %s", user)

        tickers = get_ticker(int(user[0]))

        logger.info(
            "tickers of %s: %s",
            user[2],
            tickers
        )

        for ticker in tickers:

            try:

                logger.info("ticker %s", ticker)

                dat = yf.Ticker(ticker[0])

                info = dat.info

                # First day of current month
                value = dat.history(
                    start=datetime.today().replace(day=1),
                    end=datetime.today().replace(day=2),
                    interval="1d",
                    rounding=True
                )

                if value.empty:

                    logger.warning(
                        "No monthly data for %s",
                        ticker[0]
                    )

                    continue

                first_day_of_month = value["Close"].iloc[0]

                logger.info(
                    "firstDay: %s",
                    first_day_of_month
                )

                # Latest available price
                value = dat.history()

                if value.empty:

                    logger.warning(
                        "No historical data for %s",
                        ticker[0]
                    )

                    continue

                today = value["Close"].iloc[-1]

                logger.info("today: %s", today)

                if not first_day_of_month:

                    logger.warning(
                        "Invalid first day price for %s",
                        ticker[0]
                    )

                    continue

                diff = today - first_day_of_month

                changes = diff * 100 / first_day_of_month

                percentage_change = str(round(changes, 2))

                output = (
                    "%s (%s - %s), currentPrice: %s %s, "
                    "percentageChange: %s%%"
                ) % (
                    info["longName"],
                    info["symbol"],
                    info["fullExchangeName"],
                    info["regularMarketPrice"],
                    info["currency"],
                    percentage_change,
                )

                await context.bot.send_message(
                    chat_id=user[1],
                    text=output
                )

            except Exception:

                logger.exception(
                    "Error processing ticker %s for user %s",
                    ticker[0],
                    user[2]
                )


# --------------------------------------------------
# HTTP HEALTH CHECK
# --------------------------------------------------

async def health(request):

    return web.Response(text="OK")


async def http_server():

    app = web.Application()

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)

    await runner.setup()

    port = int(os.environ.get("PORT", 10000))

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=port,
    )

    await site.start()

    logger.info(
        "HTTP server listening on 0.0.0.0:%s",
        port
    )

    await asyncio.Event().wait()


def run_http_server():

    asyncio.run(http_server())


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main() -> None:

    logger.info("Starting Telegram bot...")

    # Start HTTP server in background thread
    thread = threading.Thread(
        target=run_http_server,
        daemon=True,
    )

    thread.start()

    # Create Telegram application
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    # Conversation handler
    conv_handler = ConversationHandler(

        entry_points=[
            CommandHandler(
                "insert_ticker",
                insert_ticker
            )
        ],

        states={
            SAVE_TICKER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    save_ticker
                )
            ],
        },

        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
    )

    application.add_handler(conv_handler)

    # Echo messages
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            echo
        )
    )

    # Cronjob: every 4 hours
    application.job_queue.run_repeating(
        job,
        interval=14400,
        first=0,
    )

    # Start bot
    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# --------------------------------------------------
# ENTRY POINT
# --------------------------------------------------

if __name__ == "__main__":
    main()
