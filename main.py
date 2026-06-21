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

# Fetch the channel ID(s). This safely handles your single ID, 
# but will still work if you ever add commas back in later.
raw_channel_ids = os.getenv("DISCORD_CHANNEL_IDS", "")
if raw_channel_ids:
    DISCORD_CHANNEL_IDS = [int(cid.strip()) for cid in raw_channel_ids.split(",") if cid.strip()]
else:
    print("CRITICAL: DISCORD_CHANNEL_IDS is missing from your .env file!")
    DISCORD_CHANNEL_IDS = []

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
    print(f'Listening to Discord Channel(s): {DISCORD_CHANNEL_IDS}')

@discord_bot.event
async def on_message(message):
    # 1. Webhook / Bot Filter
    if message.webhook_id is not None:
        # ALLOW webhooks (your translator bot) through
        print(f"DEBUG: Permitting webhook message from {message.author.display_name}")
    elif message.author.bot:
        # BLOCK standard bots (like this script itself) to prevent infinite loops
        return

    # 2. Act if the message is in the registered source channel
    if message.channel.id in DISCORD_CHANNEL_IDS:
        print(f"--- DISCORD DEBUG --- Received from {message.author.display_name} in channel {message.channel.id}")

        # Format message
        sender_name = message.author.display_name
        formatted_text = f"{sender_name}:\n\n{message.content}"
        
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
                        caption=formatted_text if message.content else f"{sender_name}:",
                        message_thread_id=TELEGRAM_TOPIC_ID if TELEGRAM_TOPIC_ID != 0 else None
                    )
                    print("DEBUG: Image sent to Telegram successfully.")
                    return 

            # Handle Text-only
            if message.content:
                 await tg_bot_sender.send_message(
                    chat_id=TELEGRAM_GROUP_ID,
                    text=formatted_text,
                    message_thread_id=TELEGRAM_TOPIC_ID if TELEGRAM_TOPIC_ID != 0 else None
                )
                 print("DEBUG: Text sent to Telegram successfully.")
                 
        except Exception as e:
            print(f"CRITICAL ERROR forwarding to Telegram: {e}")


# --- TELEGRAM BOT LOGIC (Telegram -> Discord Source) ---

async def telegram_receive_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("--- TELEGRAM DEBUG ---")
    
    message = update.effective_message
    if not message:
        return

    # Ignore messages sent by bots to prevent echo loops
    if message.from_user and message.from_user.is_bot:
        print("DEBUG: Ignored bot message to prevent echo loop.")
        return

    sender_user = update.effective_user
    sender_name = sender_user.first_name or sender_user.username
    text_content = message.text or message.caption or ""
    photo_content = message.photo

    # Download image bytes into memory ONCE (if applicable)
    byte_array = None
    if photo_content:
        photo = photo_content[-1]
        tg_file = await context
