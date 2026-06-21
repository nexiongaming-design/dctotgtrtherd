from flask import Flask
from threading import Thread
import os
import sys

app = Flask(__name__)

# Global flag to track bot health
bot_status = {"discord_online": False, "telegram_online": False}

@app.route('/')
def home():
    # If either bot drops out after initially starting, fail the health check
    if not bot_status["discord_online"] or not bot_status["telegram_online"]:
        return "Bot system failure!", 500
    return "Bot is running!", 200

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True # Allows the thread to die instantly if the main program exits
    t.start()
