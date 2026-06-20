import os
import discord
from discord.ext import commands
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from deep_translator import GoogleTranslator
from dotenv import load_dotenv
import asyncio
import requests
import io

# --- START THE DUMMY WEB SERVER ---
from keep_alive import keep_alive
keep_alive() 
# ----------------------------------

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

# Initialize Telegram bot for sending
tg_bot_sender = Bot(token=TELEGRAM_TOKEN)

# Initialize Discord bot
intents = discord.Intents.default()
intents.message_content = True # REQUIRED
discord_bot = commands.Bot(command_prefix="!", intents=intents)

# --- INTERNAL HELPER FUNCTIONS ---

async def discord_forward_helper(target_channel, content, file=None, original_message=None):
    """Generic function to send text/files to Discord with sender info."""
    sender_name = original_message.author.global_name or original_message.author.name
    avatar_url = original_message.author.display_avatar.url
    
    formatted_content = f"**{sender_name}** from Discord Source:"
    
    # Send content only if it exists
    if content:
        formatted_content += f"\n\n{content}"

    # Embed creation for better avatar support
    embed = discord.Embed(description=formatted_content)
    embed.set_author(name=sender_name, icon_url=avatar_url)

    if file:
        await target_channel.send(embed=embed, file=file)
    else:
        await target_channel.send(embed=embed)


# --- DISCORD BOT LOGIC (Receiving from Discord) ---

@discord_bot.event
async def on_ready():
    print(f'Logged in to Discord as {discord_bot.user.name}')

@discord_bot.event
async def on_message(message):
    """Processes messages from Discord."""
    # Prevent bot from responding to itself
    if message.author == discord_bot.user:
        return

    # 1. Handle Multi-Channel Translation (within Discord)
    if message.channel.id == SOURCE_CHANNEL_ID and message.content:
        for lang_code, target_channel_id in LANGUAGE_MAP.items():
            target_channel = discord_bot.get_channel(target_channel_id)
            if target_channel:
                try:
                    # Translate
                    translated = GoogleTranslator(source='auto', target=lang_code).translate(message.content)
                    
                    # Prepare file if original has attachments
                    file = None
                    if message.attachments:
                        attachment = message.attachments[0]
                        if attachment.filename.lower().endswith(('png', 'jpg', 'jpeg', 'webp')):
                            # Must create a NEW file object for every send
                            response = requests.get(attachment.url)
                            file_data = io.BytesIO(response.content)
                            file = discord.File(file_data, filename=attachment.filename)

                    # Send translated content
                    await discord_forward_helper(target_channel, translated, file, message)
                    
                except Exception as e:
                    print(f"Translation Error for {lang_code}: {e}")

    # 2. Handle Forwarding to Telegram
    if message.channel.id == SOURCE_CHANNEL_ID:
        sender_name = message.author.global_name or message.author.name
        formatted_text = f"{sender_name} from Discord:\n\n{message.content}"
        
        try:
            # Handle Image forwarding to Telegram
            if message.attachments:
                attachment = message.attachments[0]
                if attachment.filename.lower().endswith(('png', 'jpg', 'jpeg', 'webp')):
                    # TG can send photo by direct URL
                    await tg_bot_sender.send_photo(
                        chat_id=TELEGRAM_GROUP_ID,
                        photo=attachment.url,
                        caption=formatted_text,
                        message_thread_id=TELEGRAM_TOPIC_ID
                    )
                    return # Stop after sending image

            # If no image, send just text
            if message.content:
                 await tg_bot_sender.send_message(
                    chat_id=TELEGRAM_GROUP_ID,
                    text=formatted_text,
                    message_thread_id=TELEGRAM_TOPIC_ID
                )
        except Exception as e:
            print(f"Error forwarding to Telegram: {e}")


# --- TELEGRAM BOT LOGIC (Receiving from Telegram) ---

async def telegram_receive_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes messages received by the Telegram Bot."""
    # 1. Filter: Only process from our specific Group
    if update.effective_chat.id != TELEGRAM_GROUP_ID:
        return

    # 2. Extract Data
    sender_user = update.effective_user
    sender_name = sender_user.first_name or sender_user.username
    text_content = update.message.text
    photo_content = update.message.photo

    # 3. Get Discord Source Channel
    source_channel = discord_bot.get_channel(SOURCE_CHANNEL_ID)
    if not source_channel:
        print("Discord Source Channel not found.")
        return

    # Formatting basic message for Discord
    discord_text = f"**{sender_name}** from Telegram:"
    if text_content:
        discord_text += f"\n\n{text_content}"
    
    # 4. Handle Text and Image Forwarding to Discord
    try:
        # Handle Images from TG
        if photo_content:
            # TG sends a list of photo sizes; get the largest
            photo = photo_content[-1]
            # Download file
            tg_file = await context.bot.get_file(photo.file_id)
            # Binary data
            file_response = requests.get(tg_file.file_path)
            file_stream = io.BytesIO(file_response.content)
            # Create Discord File object
            discord_file = discord.File(file_stream, filename="telegram_image.png")
            
            await source_channel.send(content=discord_text, file=discord_file)
        
        # Handle plain text only
        elif text_content:
            await source_channel.send(content=discord_text)

    except Exception as e:
        print(f"Error forwarding from Telegram to Discord: {e}")


# --- INTEGRATED RUNNER ---

async def main():
    # Setup Telegram Application for listening
    tg_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Add handler for text and photos
    tg_msg_filter = filters.Chat(TELEGRAM_GROUP_ID) & (filters.TEXT | filters.PHOTO)
    tg_app.add_handler(MessageHandler(tg_msg_filter, telegram_receive_handler))

    # We must run both bot loops simultaneously
    print("Starting bots...")
    
    # We use asyncio.gather to manage both loops in one async execution
    await asyncio.gather(
        discord_bot.start(DISCORD_TOKEN),
        tg_app.run_polling(drop_pending_updates=True) # run_polling is async
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Handle graceful shutdown on Ctrl+C
        print("Stopping bots...")
