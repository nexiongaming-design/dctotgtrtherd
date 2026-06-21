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

# SMART CHANNEL FETCHING: Supports both your old .env variable and the new list format
raw_channel_ids = os.getenv("DISCORD_CHANNEL_IDS", "")
if raw_channel_ids:
    DISCORD_CHANNEL_IDS = [int(cid.strip()) for cid in raw_channel_ids.split(",") if cid.strip()]
else:
    # Falls back to your existing .env variable so it works instantly
    old_id = os.getenv("DISCORD_SOURCE_CHANNEL_ID")
    DISCORD_CHANNEL_IDS = [int(old_id)] if old_id else []

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
    # 1. Ignore ALL bots (prevents duplicate loops from translator bots)
    if message.author.bot:
        return

    # 2. Ignore ALL messages sent by Webhooks
    if message.webhook_id is not None:
        return

    # 3. Act if the message is in ANY of the registered channels
    if message.channel.id in DISCORD_CHANNEL_IDS:
        print(f"--- DISCORD DEBUG --- Received from {message.author} in channel {message.channel.id}")

        # FIX: Uses display_name to perfectly match the server nickname and special characters
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
        tg_file = await context.bot.get_file(photo.file_id)
        byte_array = await tg_file.download_as_bytearray()

    # Format the ORIGINAL message
    original_discord_text = f"**{sender_name}**"
    if text_content:
        original_discord_text += f"\n\n{text_content}"
    
    # Loop through connected Discord channels and send the Telegram message
    for channel_id in DISCORD_CHANNEL_IDS:
        target_channel = discord_bot.get_channel(channel_id)
        
        if not target_channel:
            print(f"Warning: Discord Channel ID {channel_id} not found/bot lacks access.")
            continue

        try:
            if byte_array:
                # We must recreate the BytesIO stream for EVERY channel loop.
                file_stream = io.BytesIO(byte_array)
                discord_file = discord.File(file_stream, filename="telegram_image.png")
                await target_channel.send(content=original_discord_text, file=discord_file)
            elif text_content:
                await target_channel.send(content=original_discord_text)
                
            print(f"DEBUG: Successfully bridged from Telegram to Discord Channel {channel_id}.")
        except Exception as e:
            print(f"Error forwarding original to Discord Channel {channel_id}: {e}")


# --- INTEGRATED RUNNER ---

async def main():
    global tg_bot_sender # Access the global variable
    
    # Setup Telegram Application
    tg_app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .get_updates_read_timeout(30.0)
        .build()
    )

    # Bind the sender bot AFTER the event loop has started
    tg_bot_sender = tg_app.bot 

    tg_msg_filter = filters.Chat(TELEGRAM_GROUP_ID) & (filters.TEXT | filters.PHOTO)
    tg_app.add_handler(MessageHandler(tg_msg_filter, telegram_receive_handler))

    print("Starting Telegram Bot...")
    # Initialize and start polling
    await tg_app.initialize()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    await tg_app.start()

    print("Starting Discord Bot...")
    try:
        # Start Discord
        await discord_bot.start(DISCORD_TOKEN)
    finally:
        # This code runs if Discord crashes or shuts down
        print("Shutting down bots...")
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        await discord_bot.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Critical Error: {e}")
