import os
import discord
from discord.ext import commands
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv
import asyncio
import io

# --- 1. START THE DUMMY WEB SERVER ---
from keep_alive import keep_alive
keep_alive() 
# -------------------------------------

# Load secrets
load_dotenv()

# --- CONFIGURATION ---
# Discord IDs
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# NEW: Fetch multiple channel IDs as a comma-separated list
# Example .env entry: DISCORD_CHANNEL_IDS=123456789,987654321,555555555
raw_channel_ids = os.getenv("DISCORD_CHANNEL_IDS", "")
DISCORD_CHANNEL_IDS = [int(channel_id.strip()) for channel_id in raw_channel_ids.split(",") if channel_id.strip()]

# Telegram IDs
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_GROUP_ID = int(os.getenv("TELEGRAM_GROUP_ID"))
TELEGRAM_TOPIC_ID = int(os.getenv("TELEGRAM_TOPIC_ID"))

# Initialize as None to avoid Event Loop conflicts. 
tg_bot_sender = None

# Initialize Discord bot
intents = discord.Intents.default()
intents.message_content = True # REQUIRED
discord_bot = commands.Bot(command_prefix="!", intents=intents)


# --- DISCORD BOT LOGIC (Discord Source -> Telegram) ---

@discord_bot.event
async def on_ready():
    print(f'Logged in to Discord as {discord_bot.user.name}')
    print(f'Listening to Discord Channels: {DISCORD_CHANNEL_IDS}')

@discord_bot.event
async def on_message(message):
    # 1. Ignore ALL bots (prevents echo loops from translator bots and our own bot)
    if message.author.bot:
        return

    # 2. Ignore ALL messages sent by Webhooks (prevents webhook translation loops)
    if message.webhook_id is not None:
        return

    # 3. Act if the message is in ANY of the Source Channels
    if message.channel.id in DISCORD_CHANNEL_IDS:
        print(f"--- DISCORD DEBUG --- Received from {message.author} in channel {message.channel.
