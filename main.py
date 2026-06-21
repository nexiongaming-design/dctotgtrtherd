import os
import discord
from discord.ext import commands
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from deep_translator import GoogleTranslator
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
SOURCE_CHANNEL_ID = int(os.getenv("DISCORD_SOURCE_CHANNEL_ID"))
EN_CHANNEL_ID = int(os.getenv("DISCORD_EN_CHANNEL_ID"))
FR_CHANNEL_ID = int(os.getenv("DISCORD_FR_CHANNEL_ID"))
DE_CHANNEL_ID = int(os.getenv("DISCORD_DE_CHANNEL_ID"))
IT_CHANNEL_ID = int(os.getenv("DISCORD_IT_CHANNEL_ID"))
ES_CHANNEL_ID = int(os.getenv("DISCORD_ES_CHANNEL_ID"))
NL_CHANNEL_ID = int(os.getenv("DISCORD_NL_CHANNEL_ID"))

# Mapping for the translation function
LANGUAGE_MAP = {
    'en': EN_CHANNEL_ID,
    'fr': FR_CHANNEL_ID,
    'de': DE_CHANNEL_ID,
    'it': IT_CHANNEL_ID,
    'es': ES_CHANNEL_ID,
    'nl': NL_CHANNEL_ID
}

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


# --- DISCORD BOT LOGIC (Discord -> Telegram ONLY) ---

@discord_bot.event
async def on_ready():
    print(f'Logged in to Discord as {discord_bot.user.name}')

@discord_bot.event
async def on_message(message):
    # 1. Ignore if sent by the bot (Prevents infinite loops)
    if message.author.id == discord_bot.user.id:
        return

    # 2. Double-check for signature (Prevents loops from translated messages)
    if "\u200b" in message.content:
        return

    # 3. Check if message is in the SOURCE channel OR any of the LANGUAGE channels
    if message.channel.id == SOURCE_CHANNEL_ID or message.channel.id in LANGUAGE_MAP.values():
        print(f"--- DISCORD DEBUG --- Received from {message.author} in {message.channel.name}")

        sender_name = message.author.global_name or message.author.name
        text_to_forward = message.content

        # Optional: Translate messages from language channels to English for Telegram
        if message.channel.id in LANGUAGE_MAP.values() and text_to_forward:
            try:
                # Translates whatever language they typed in back to English
                text_to_forward = GoogleTranslator(source='auto', target='en').translate(text_to_forward)
            except Exception as e:
                print(f"Translation Error (Discord -> Telegram): {e}")

        # Add the channel name so Telegram users know where it came from
        formatted_text = f"{sender_name} (via {message.channel.name}):\n\n{text_to_forward}"
        
        try:
            print(f"DEBUG: Attempting to send to Telegram (ChatID: {TELEGRAM_GROUP_ID})")
            
            # Handle Image
            if message.attachments:
                attachment = message.attachments[0]
                if attachment.filename.lower().endswith(('png', 'jpg', 'jpeg', 'webp')):
                    image_bytes = await attachment.read()
                    
                    await tg_bot_sender.send_photo(
                        chat_id=TELEGRAM_GROUP_ID,
                        photo=image_bytes,
