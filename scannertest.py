import os
import json
import logging
import asyncio
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import discord
import psycopg2
from psycopg2.extras import RealDictCursor

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

# PostgreSQL connection
DATABASE_URL = os.environ['DATABASE_URL']

# Shallow scan folders
SHALLOW_FOLDERS = {
    "Sofia [Model Content Upload]": "1MBUfAv_MjSuxe697zla6rwuwFeHVBM5O",
    "Katy [Model Content Upload]": "1M5rkyM5wGd293oUclD5h6882lA4SqIZv",
    "Nora [Model Content Upload]": "1nQrnYByAiQ0j26Bxf-CLBpldNMfVTTPf",
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
    "Sally [Model Content Upload]": "1rWKITODxvhWAV55A_qtsxwZPAzUKQlU2"
}

# Deep scan folder
DEEP_MODEL_NAME = "Claire [Model Content Upload]"
DEEP_FOLDER_ID = "13iy_aJsGKb3r4GDcK-37rppnuzNkc2sh"

logging.basicConfig(level=logging.INFO)

# ---------------- DATABASE ----------------
def init_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    # create tables if not exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            file_id TEXT PRIMARY KEY,
            name TEXT,
            size BIGINT,
            full_path TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scanned_folders (
            folder_id TEXT PRIMARY KEY
        )
    """)
    conn.commit()
    return conn, cur

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

# ---------------- SCAN FUNCTIONS ----------------
async def scan_shallow(model_name, folder_id, channel, cur, conn):
    logging.info(f"Checking shallow: {model_name}")
    try:
        subfolders = list_subfolders(folder_id)
        for sf in subfolders:
            full_path = f"{model_name}>{sf['name']}"
            cur.execute("SELECT 1 FROM files WHERE file_id=%s", (sf['id'],))
            if cur.fetchone() is None:
                cur.execute(
                    "INSERT INTO files (file_id, name, size, full_path) VALUES (%s, %s, %s, %s)",
                    (sf['id'], sf['name'], 0, full_path)
                )
                conn.commit()
                await channel.send(f"<@&{ROLE_ID}> 📁 New folder detected: {full_path}")
    except Exception as e:
        logging.error(f"Shallow scan error: {e}")

async def scan_deep(folder_name, folder_id, channel, cur, conn, parent_path=None):
    if parent_path is None:
        parent_path = folder_name
    try:
        files = list_files(folder_id)
        for f in files:
            full_path = f"{parent_path}>{f['name']}"
            cur.execute("SELECT 1 FROM files WHERE file_id=%s", (f['id'],))
            if cur.fetchone() is None:
                cur.execute(
                    "INSERT INTO files (file_id, name, size, full_path) VALUES (%s, %s, %s, %s)",
                    (f['id'], f['name'], int(f.get('size', 0)), full_path)
                )
                conn.commit()
                await channel.send(f"<@&{ROLE_ID}> 📄 New file detected: {full_path}")

        subfolders = list_subfolders(folder_id)
        for sf in subfolders:
            await scan_deep(sf['name'], sf['id'], channel, cur, conn, parent_path=f"{parent_path}>{sf['name']}")
    except Exception as e:
        logging.error(f"Deep scan error: {e}")

# ---------------- WATCHER LOOP ----------------
async def watcher_loop(channel):
    conn, cur = init_db()
    await client.wait_until_ready()
    while True:
        logging.info(f"{datetime.utcnow().isoformat()} - Starting scan cycle")

        # shallow scans
        for model_name, folder_id in SHALLOW_FOLDERS.items():
            await scan_shallow(model_name, folder_id, channel, cur, conn)

        # deep scan
        await scan_deep(DEEP_MODEL_NAME, DEEP_FOLDER_ID, channel, cur, conn)

        logging.info(f"{datetime.utcnow().isoformat()} - Scan complete, restarting immediately")
        await asyncio.sleep(5)

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

# ---------------- RUN ----------------
client.run(BOT_TOKEN)

