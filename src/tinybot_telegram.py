import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from tinybot_core import TinyBotCore
from utils import load_secrets

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Core
load_secrets()
tinybot_core = TinyBotCore()

# Authorized User ID (from env)
AUTHORIZED_USER_ID = os.environ.get("TELEGRAM_AUTHORIZED_USER_ID")
if AUTHORIZED_USER_ID:
    try:
        AUTHORIZED_USER_ID = int(AUTHORIZED_USER_ID)
    except ValueError:
        logger.error("TELEGRAM_AUTHORIZED_USER_ID must be an integer.")
        AUTHORIZED_USER_ID = None

# API Token (from env)
API_TOKEN = os.environ.get("TELEGRAM_API_TOKEN")

if not API_TOKEN:
    logger.error("TELEGRAM_API_TOKEN not found in environment.")
    exit(1)

# Initialize Bot and Dispatcher
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        await message.answer("Access denied. *boop*")
        return
    await message.answer(f"TinyBot connected! *clank* Active agent: {tinybot_core.session_state['active_agent_key']}")

@dp.message()
async def handle_message(message: Message):
    if AUTHORIZED_USER_ID and message.from_user.id != AUTHORIZED_USER_ID:
        logger.warning(f"Unauthorized access attempt from User ID: {message.from_user.id}")
        return

    if not message.text:
        return

    # Pass input to TinyBotCore
    response = tinybot_core.process_user_input(message.text)

    if response == "TINYBOT_EXIT_SIGNAL":
        await message.answer("Shutting down... *clank*")
        tinybot_core._perform_exit_sequence()
        # Note: In a real polling scenario, you'd need to stop the loop here.
        # For simplicity, we'll let the process be killed.
        exit(0)
    else:
        # aiogram handles message splitting if content is too long
        # but for now, we'll just send it.
        await message.answer(response)

async def main():
    logger.info("Starting Telegram Bot... *beep*")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually. *clank*")
