import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import discord

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ['BOT_TOKEN']
GUILD_ID = int(os.environ['GUILD_ID'])       # new Railway env var
CHANNEL_ID = int(os.environ['CHANNEL_ID'])
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
ROLE_ID = 1467928994665205811

# Google service account from env
credentials_dict = json.loads(os.environ['SERVICE_ACCOUNT_JSON'])
credentials = Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

# All folders will be deep scanned
FOLDERS = {
    "Sofia [Model Content Upload]": "1MBUfAv_MjSuxe697zla6rwuwFeHVBM5O",
    "Katy [Model Content Upload]": "1M5rkyM5wGd293oUclD5h6882lA4SqIZv",
    "Lexi [Model Content Upload]": "1O35U73VWpMn2FJsDhhHA6OF9mGEEcdAo",
    "Heather [PPV Upload]": "1uNdYQK3kgnOA4qTnCSIb6QcQUJ7gnBne",
    "Heather [OF Pics Upload]": "1Eg7JUh3PoUiHbKEVQEsKfpr5dY1nsriQ",
    "Heather [OF Vids Upload]": "1ny9ASKmyC90Ai8tOuTqkJdb3ZCQp_8Hk",
    "Kylie B [Model Content Upload]": "1OC8QIz_1aEtKg9q0xOoxIUuRIwmqyIe1",
    "Sara [Model Content Upload]": "1qw5DwgOmrkjHtkJqyjHcG4__enweerAU",
    "Emily [Model Content Upload]": "19ioe850BAFPNvOAGB955q38ZTjmXluWP",
    "Shea [Model Content Upload]": "1KJkG3YEoalb3VVrJZLj1wwaA0dZxyg3I",
    "Eevie [Model Content Upload]": "1Wmx9zx0blbVHkcrMYL_1_gXsHjNLvaO_",
    "Kylie C [Model Content Upload]": "1tFGXI-ggK6reKzMrGC2RBk17_20a4l3Q",
    "Sally [Model Content Upload]": "1rWKITODxvhWAV55A_qtsxwZPAzUKQlU2",
    "Claire [Model Content Upload]": "13iy_aJsGKb3r4GDcK-37rppnuzNkc2sh"
}

logging.basicConfig(level=logging.INFO)

# ---------------- GOOGLE DRIVE ----------------
def list_subfolders(parent_id):
    results = drive_service.files().list(
        q=f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)"
    ).execute()
    return results.get('files', [])

def list_files(parent_id):
    results = drive_service.files().list(
        q=f"'{parent_id}' in parents and trashed=false",
        fields="files(id, name, size)"
    ).execute()
    return results.get('files', [])

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
client = discord.Client(intents=intents)

# Track pending notifications for Sara (24h delay)
sara_pending_notifications = []

# ---------------- SCAN FUNCTIONS ----------------
async def scan_deep(folder_name, folder_id, channel, seen_ids, parent_path=None):
    if parent_path is None:
        parent_path = folder_name
    
    # Check if this is Sara's folder
    is_sara = folder_name == "Sara [Model Content Upload]"
    
    try:
        files = list_files(folder_id)
        for f in files:
            full_path = f"{parent_path}>{f['name']}"
            if f['id'] not in seen_ids:
                seen_ids.add(f['id'])
                message = f"<@&{ROLE_ID}> 📄 New file detected: {full_path}"
                
                if is_sara:
                    # Delay notification by 24 hours for Sara
                    notification_time = datetime.utcnow() + timedelta(hours=24)
                    sara_pending_notifications.append({
                        'message': message,
                        'send_at': notification_time
                    })
                    logging.info(f"Sara notification scheduled for {notification_time.isoformat()}: {full_path}")
                else:
                    await channel.send(message)

        subfolders = list_subfolders(folder_id)
        for sf in subfolders:
            if sf['id'] not in seen_ids:
                seen_ids.add(sf['id'])
                message = f"<@&{ROLE_ID}> 📁 New folder detected: {parent_path}>{sf['name']}"
                
                if is_sara:
                    # Delay notification by 24 hours for Sara
                    notification_time = datetime.utcnow() + timedelta(hours=24)
                    sara_pending_notifications.append({
                        'message': message,
                        'send_at': notification_time
                    })
                    logging.info(f"Sara notification scheduled for {notification_time.isoformat()}: {parent_path}>{sf['name']}")
                else:
                    await channel.send(message)
                    
            await scan_deep(sf['name'], sf['id'], channel, seen_ids, parent_path=f"{parent_path}>{sf['name']}")
    except Exception as e:
        logging.error(f"Deep scan error: {e}")

# ---------------- SARA NOTIFICATION HANDLER ----------------
async def sara_notification_loop(channel):
    """Check and send pending Sara notifications after 24 hours"""
    await client.wait_until_ready()
    while True:
        now = datetime.utcnow()
        pending_to_send = []
        remaining = []
        
        for notification in sara_pending_notifications:
            if now >= notification['send_at']:
                pending_to_send.append(notification)
            else:
                remaining.append(notification)
        
        # Send all notifications that are ready
        for notification in pending_to_send:
            try:
                await channel.send(notification['message'])
                logging.info(f"Sent delayed Sara notification: {notification['message']}")
            except Exception as e:
                logging.error(f"Error sending Sara notification: {e}")
        
        # Update the list to only keep pending notifications
        sara_pending_notifications.clear()
        sara_pending_notifications.extend(remaining)
        
        # Check every 10 minutes
        await asyncio.sleep(10 * 60)

# ---------------- WATCHER LOOP ----------------
async def watcher_loop(channel):
    await client.wait_until_ready()
    seen_ids = set()
    while True:
        logging.info(f"{datetime.utcnow().isoformat()} - Starting scan cycle")
        for model_name, folder_id in FOLDERS.items():
            await scan_deep(model_name, folder_id, channel, seen_ids)

        logging.info(f"{datetime.utcnow().isoformat()} - Scan complete, sleeping for 3 hours")
        await asyncio.sleep(3 * 60 * 60)

# ---------------- DISCORD EVENTS ----------------
@client.event
async def on_ready():
    logging.info("bot connected")

    # log all guilds the bot is in
    for guild in client.guilds:
        logging.info(f"bot is in guild: {guild.name} ({guild.id})")

    # fetch the guild by GUILD_ID
    guild = discord.utils.get(client.guilds, id=GUILD_ID)
    if not guild:
        logging.error(f"Bot is not in guild with ID {GUILD_ID}")
        return

    # fetch the channel from the guild
    channel = guild.get_channel(CHANNEL_ID)
    if not channel:
        logging.error(f"Channel with ID {CHANNEL_ID} not found in guild {guild.name}")
        return

    asyncio.create_task(watcher_loop(channel))
    asyncio.create_task(sara_notification_loop(channel))

# ---------------- RUN ----------------
client.run(BOT_TOKEN)


