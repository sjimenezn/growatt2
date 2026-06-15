import pytz
from flask import Flask, render_template, render_template_string, jsonify, request, send_file, redirect, url_for
import threading
import pprint
import json
import os
import time
import requests
from datetime import datetime, timedelta
from growattServer import GrowattApi
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import yt_dlp
import re

# --- YouTube Downloader HTML Template ---
YT_DOWNLOADER_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>YouTube Downloader - 720p MP4</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 1rem;
            background: #0f0f0f;
            color: #f1f1f1;
        }
        .container {
            background: #1f1f1f;
            border-radius: 24px;
            padding: 1.5rem;
            box-shadow: 0 8px 20px rgba(0,0,0,0.5);
        }
        h1 {
            font-size: 1.5rem;
            margin: 0 0 0.25rem 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .sub {
            color: #aaa;
            margin-bottom: 1.5rem;
            font-size: 0.85rem;
        }
        .search-area {
            display: flex;
            gap: 10px;
            margin-bottom: 1.5rem;
            flex-wrap: wrap;
        }
        input {
            flex: 1;
            padding: 12px 16px;
            font-size: 1rem;
            border: none;
            border-radius: 40px;
            background: #2a2a2a;
            color: white;
            outline: none;
            min-width: 200px;
        }
        input:focus {
            background: #333;
            box-shadow: 0 0 0 2px #3ea6ff;
        }
        button {
            background: #3ea6ff;
            border: none;
            padding: 0 20px;
            border-radius: 40px;
            font-weight: bold;
            font-size: 0.9rem;
            cursor: pointer;
            transition: 0.2s;
            color: #0f0f0f;
        }
        button:hover {
            background: #5cb3ff;
            transform: scale(0.98);
        }
        .loading {
            text-align: center;
            padding: 2rem;
            color: #aaa;
        }
        .results-grid {
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-top: 1rem;
        }
        .video-card {
            background: #2a2a2a;
            border-radius: 16px;
            display: flex;
            align-items: center;
            gap: 1rem;
            padding: 0.75rem;
            transition: 0.1s;
            flex-wrap: wrap;
        }
        .video-card:hover {
            background: #333;
        }
        .thumbnail {
            width: 100px;
            border-radius: 8px;
            flex-shrink: 0;
        }
        .video-info {
            flex: 1;
            min-width: 150px;
        }
        .video-title {
            font-weight: 600;
            margin-bottom: 6px;
            font-size: 0.9rem;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .video-meta {
            font-size: 0.75rem;
            color: #aaa;
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }
        .download-btn {
            background: #2e7d32;
            color: white;
            padding: 8px 16px;
            border-radius: 40px;
            text-decoration: none;
            font-weight: bold;
            font-size: 0.85rem;
            white-space: nowrap;
        }
        .download-btn:hover {
            background: #1b5e20;
        }
        .error {
            background: #8b0000;
            padding: 1rem;
            border-radius: 12px;
            margin: 1rem 0;
        }
        .nav-links {
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }
        .nav-links a {
            color: #3ea6ff;
            text-decoration: none;
            font-size: 0.9rem;
        }
        hr {
            border-color: #333;
            margin: 1rem 0;
        }
        @media (max-width: 600px) {
            .video-card {
                flex-direction: column;
                text-align: center;
            }
            .thumbnail {
                width: 160px;
            }
            .search-area {
                flex-direction: column;
            }
            button {
                padding: 10px;
            }
        }
    </style>
</head>
<body>
<div class="container">
    <div class="nav-links">
        <a href="/">🏠 Home</a>
        <a href="/logs">📊 Logs</a>
        <a href="/console">📝 Console</a>
        <a href="/yt">📥 YouTube Downloader</a>
    </div>
    
    <h1>📥 YouTube Downloader</h1>
    <div class="sub">Search YouTube → Click Download → Get 720p MP4 (or best available)</div>

    <div class="search-area">
        <input type="text" id="searchInput" placeholder="Paste YouTube URL or search term...">
        <button id="searchBtn">🔍 Search / Fetch</button>
    </div>
    <div id="resultsArea">
        <div class="loading">💡 Paste a YouTube URL and click Search, or type keywords to search.</div>
    </div>
    <hr>
    <div style="font-size: 0.7rem; text-align: center; color: #555;">
        ⚡ Downloads 720p MP4 • Falls back to best quality if 720p unavailable
    </div>
</div>

<script>
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    const resultsArea = document.getElementById('resultsArea');

    function isYouTubeUrl(url) {
        return url.includes('youtube.com/watch') || url.includes('youtu.be/');
    }

    searchBtn.addEventListener('click', () => {
        const query = searchInput.value.trim();
        if (!query) return;
        
        if (isYouTubeUrl(query)) {
            fetchVideoInfo(query);
        } else {
            searchYouTube(query);
        }
    });

    async function searchYouTube(searchTerm) {
        resultsArea.innerHTML = '<div class="loading">🔎 Searching videos...</div>';
        try {
            const response = await fetch(`/api/yt/search?q=${encodeURIComponent(searchTerm)}`);
            const data = await response.json();
            if (data.error) throw new Error(data.error);
            renderVideoList(data.videos);
        } catch (err) {
            resultsArea.innerHTML = `<div class="error">❌ Search failed: ${err.message}</div>`;
        }
    }

    async function fetchVideoInfo(url) {
        resultsArea.innerHTML = '<div class="loading">📡 Fetching video details...</div>';
        try {
            const response = await fetch(`/api/yt/info?url=${encodeURIComponent(url)}`);
            const data = await response.json();
            if (data.error) throw new Error(data.error);
            renderVideoList([data]);
        } catch (err) {
            resultsArea.innerHTML = `<div class="error">❌ Failed to get video: ${err.message}</div>`;
        }
    }

    function formatDuration(duration) {
        if (!duration) return '?';
        return duration;
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/[&<>]/g, function(m) {
            if (m === '&') return '&amp;';
            if (m === '<') return '&lt;';
            if (m === '>') return '&gt;';
            return m;
        });
    }

    function renderVideoList(videos) {
        if (!videos || videos.length === 0) {
            resultsArea.innerHTML = '<div class="loading">😞 No videos found.</div>';
            return;
        }
        
        const html = `
            <div class="results-grid">
                ${videos.map(video => `
                    <div class="video-card">
                        <img class="thumbnail" src="${video.thumbnail}" alt="thumbnail" onerror="this.src='https://placehold.co/120x68?text=No+Image'">
                        <div class="video-info">
                            <div class="video-title">${escapeHtml(video.title)}</div>
                            <div class="video-meta">
                                <span>⏱️ ${formatDuration(video.duration)}</span>
                                <span>📺 ${escapeHtml(video.author)}</span>
                            </div>
                        </div>
                        <a class="download-btn" href="/api/yt/download?url=${encodeURIComponent(video.webpage_url)}">⬇️ Download 720p</a>
                    </div>
                `).join('')}
            </div>
        `;
        resultsArea.innerHTML = html;
    }

    // Allow Enter key to search
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') searchBtn.click();
    });
</script>
</body>
</html>
'''

# --- Pre-computation Logging ---
console_logs = []
def log_message(message):
    timestamped = f"{(datetime.now() - timedelta(hours=5)).strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now = time.time()
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 6000]

# --- Credentials ---
username1 = "vospina"
password1 = "Vospina.2025"

# --- Telegram Config ---
TELEGRAM_TOKEN = "7653969082:AAGGuY6-sZz0KbVDTa0zfNanMF4MH1vP_oo" # <--- YOUR CURRENT TOKEN
CHAT_IDS = ["5715745951", "7524705169", "7812545729", "7862573365", "7650630450"]
chat_log = set()

# Global variable to control Telegram bot state
telegram_enabled = False
updater = None  # Global reference for the Updater object
dp = None       # Global reference for the Dispatcher object

# --- YouTube Downloader Config ---
DOWNLOAD_FOLDER = 'downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# --- Flask App ---
app = Flask(__name__)

GROWATT_USERNAME = "vospina"
PASSWORD_CRC = "0c4107c238d57d475d4660b07b2f043e"
STORAGE_SN = "BNG7CH806N"
PLANT_ID = "2817170"

HEADERS = {
    'User-Agent': 'Mozilla/5.5',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest'
}

session = requests.Session()

def growatt_login2():
    data = {
        'account': GROWATT_USERNAME,
        'password': '',
        'validateCode': '',
        'isReadPact': '0',
        'passwordCrc': PASSWORD_CRC
    }
    session.post('https://server.growatt.com/login', headers=HEADERS, data=data)

def get_today_date_utc_minus_5():
    now = datetime.utcnow() - timedelta(hours=5)
    return now.strftime('%Y-%m-%d')


# Growatt API
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})

# --- Shared Data ---
current_data = {}
last_processed_time = "Never"
last_successful_growatt_update_time = "Never" # This will be the time of the last *fresh* data received

fetched_data = {}

def send_telegram_message(message):
    global updater
    if telegram_enabled and updater and updater.running:
        for chat_id in CHAT_IDS:
            for attempt in range(3):
                try:
                    updater.bot.send_message(chat_id=chat_id, text=message)
                    log_message(f"✅ Message sent to {chat_id}")
                    break
                except Exception as e:
                    log_message(f"❌ Attempt {attempt + 1} failed to send message to {chat_id}: {e}")
                    time.sleep(5)
                    if attempt == 2:
                        log_message(f"❌ Failed to send message to {chat_id} after 3 attempts")
    else:
        log_message(f"Telegram not enabled or updater not running. Message not sent: {message}")

def login_growatt():
    log_message("🔄 Attempting Growatt login...")

    try:
        login_response = api.login(username1, password1)
        fetched_data['login_response'] = login_response
        user = login_response.get('user', {})
        user_id = user.get('id')
        fetched_data['user_id'] = user_id
        fetched_data['cpower_token'] = user.get('cpowerToken')
        fetched_data['cpower_auth'] = user.get('cpowerAuth')
        fetched_data['account_name'] = user.get('accountName')
        fetched_data['email'] = user.get('email')
        fetched_data['last_login_time'] = user.get('lastLoginTime')
        fetched_data['user_area'] = user.get('area')
        log_message("✅ Login successful!")
    except Exception as e:
        log_message(f"❌ Login failed: {e}")
        return None, None, None, None

    try:
        plant_info = api.plant_list(user_id)
        fetched_data['plant_info'] = plant_info
        plant_data = plant_info['data'][0]
        plant_id = plant_data['plantId']
        fetched_data['plant_id'] = plant_id
        fetched_data['plant_name'] = plant_data['plantName']
        fetched_data['plant_total_data'] = plant_info.get('totalData', {})
    except Exception as e:
        log_message(f"❌ Failed to retrieve plant info: {e}")
        return None, None, None, None

    try:
        inverter_info = api.inverter_list(plant_id)
        fetched_data['inverter_info'] = inverter_info
        inverter_data = inverter_info[0]
        inverter_sn = inverter_data['deviceSn']
        datalog_sn = inverter_data.get('datalogSn', 'N/A')
        fetched_data['inverter_sn'] = inverter_sn
        fetched_data['datalog_sn'] = datalog_sn
        fetched_data['inverter_alias'] = inverter_data.get('deviceAilas')
        fetched_data['inverter_capacity'] = inverter_data.get('capacity')
        fetched_data['inverter_energy'] = inverter_data.get('energy')
        fetched_data['inverter_active_power'] = inverter_data.get('activePower')
        fetched_data['inverter_apparent_power'] = inverter_data.get('apparentPower')
        fetched_data['inverter_status'] = inverter_data.get('deviceStatus')
    except Exception as e:
        log_message(f"❌ Failed to retrieve inverter info: {e}")
        return None, None, None, None

    try:
        storage_detail = api.storage_detail(inverter_sn)
        fetched_data['storage_detail'] = storage_detail
    except Exception as e:
        log_message(f"❌ Failed to retrieve storage detail: {e}")
        fetched_data['storage_detail'] = {}

    log_message(f"🌿 User ID: {user_id}")
    log_message(f"🌿 Plant ID: {plant_id}")
    log_message(f"🌿 Inverter SN: {inverter_sn}")
    log_message(f"🌿 Datalogger SN: {datalog_sn}")

    return user_id, plant_id, inverter_sn, datalog_sn

def monitor_growatt():
    global last_processed_time, last_successful_growatt_update_time, current_data
    threshold = 80

    loop_counter = 0
    user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None

    while True:
        current_loop_datetime_utc_minus_5 = datetime.now() - timedelta(hours=5)
        current_loop_time_str = current_loop_datetime_utc_minus_5.strftime("%Y-%m-%d %H:%M:%S")

        try:
            if user_id is None or plant_id is None or inverter_sn is None or datalog_sn is None:
                log_message("Attempting to acquire Growatt IDs (re-login or initial login).")
                user_id, plant_id, inverter_sn, datalog_sn = login_growatt()
                if user_id is None:
                    log_message("Growatt login/ID fetching failed. Retrying in 60 seconds.")
                    time.sleep(60)
                    continue

            raw_growatt_data = api.storage_detail(inverter_sn)

            new_ac_input_v = raw_growatt_data.get("vGrid", "N/A")
            new_ac_input_f = raw_growatt_data.get("freqGrid", "N/A")
            new_ac_output_v = raw_growatt_data.get("outPutVolt", "N/A")
            new_ac_output_f = raw_growatt_data.get("freqOutPut", "N/A")
            new_load_w = raw_growatt_data.get("activePower", "N/A")
            new_battery_pct = raw_growatt_data.get("capacity", "N/A")

            last_successful_growatt_update_time = current_loop_time_str

            current_data.update({
                "ac_input_voltage": new_ac_input_v,
                "ac_input_frequency": new_ac_input_f,
                "ac_output_voltage": new_ac_output_v,
                "ac_output_frequency": new_ac_output_f,
                "load_power": new_load_w,
                "battery_capacity": new_battery_pct,
                "user_id": user_id,
                "plant_id": plant_id,
                "inverter_sn": inverter_sn,
                "datalog_sn": datalog_sn
            })

            last_processed_time = current_loop_time_str

            # Simplified Telegram alerting - send immediate alerts without confirmation delays
            if telegram_enabled and current_data.get("ac_input_voltage") != "N/A":
                try:
                    current_ac_input_v_float = float(current_data.get("ac_input_voltage"))
                except (ValueError, TypeError):
                    current_ac_input_v_float = 0.0

                alert_timestamp = last_successful_growatt_update_time
                
                # Grid outage detection
                if current_ac_input_v_float < threshold:
                    msg = f"""🔴🔴¡Se fue la luz en Acacías!🔴🔴
    🕒 Hora--> {alert_timestamp}
Nivel de batería     : {raw_growatt_data.get('capacity', 'N/A')} %
Voltaje de la red    : {current_ac_input_v_float} V / {raw_growatt_data.get('freqGrid', 'N/A')} Hz
Voltaje del inversor: {raw_growatt_data.get('outPutVolt', 'N/A')} V / {raw_growatt_data.get('freqOutPut', 'N/A')} Hz
Consumo actual     : {raw_growatt_data.get('activePower', 'N/A')} W"""
                    send_telegram_message(msg)
                # Grid restoration detection
                elif current_ac_input_v_float >= threshold:
                    msg = f"""✅✅¡Llegó la luz en Acacías!✅✅
    🕒 Hora--> {alert_timestamp}
Nivel de batería     : {raw_growatt_data.get('capacity', 'N/A')} %
Voltaje de la red    : {current_ac_input_v_float} V / {raw_growatt_data.get('freqGrid', 'N/A')} Hz
Voltaje del inversor: {raw_growatt_data.get('outPutVolt', 'N/A')} V / {raw_growatt_data.get('freqOutPut', 'N/A')} Hz
Consumo actual     : {raw_growatt_data.get('activePower', 'N/A')} W"""
                    send_telegram_message(msg)

        except Exception as e_inner:
            log_message(f"❌ Error during Growatt data fetch or processing (API error): {e_inner}")
            # Reset IDs to force a re-login on the next attempt
            user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None

        time.sleep(60)

# Cleanup old downloads every hour
def cleanup_old_downloads():
    """Delete downloads older than 1 hour"""
    while True:
        time.sleep(3600)  # Run every hour
        now = time.time()
        for filename in os.listdir(DOWNLOAD_FOLDER):
            filepath = os.path.join(DOWNLOAD_FOLDER, filename)
            try:
                if os.path.isfile(filepath) and (now - os.path.getmtime(filepath)) > 3600:
                    os.remove(filepath)
                    log_message(f"🗑️ Cleaned up old download: {filename}")
            except Exception as e:
                log_message(f"⚠️ Could not delete {filename}: {e}")

# Telegram Handlers
def start(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    update.message.reply_text("¡Bienvenido al monitor Growatt! Usa /status para ver el estado del inversor.")

def send_status(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    timestamp = (datetime.now() - timedelta(hours=5)).strftime("%H:%M:%S")
    msg = f"""⚡ /status Estado del Inversor ⚡
        🕒 Hora--> {timestamp}
Voltaje Red          : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje Inversor   : {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo             : {current_data.get('load_power', 'N/A')} W
Batería                 : {current_data.get('battery_capacity', 'N/A')}%"""
    try:
        update.message.reply_text(msg)
        log_message(f"✅ Status sent to {update.effective_chat.id}")
    except Exception as e:
        log_message(f"❌ Failed to send status to {update.effective_chat.id}: {e}")

def send_chatlog(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    ids = "\n".join(str(cid) for cid in chat_log)
    update.message.reply_text(f"IDs registrados:\n{ids}")

def stop_bot_telegram_command(update: Update, context: CallbackContext):
    update.message.reply_text("Bot detenido.")
    log_message("Bot detenido por comando /stop")
    global telegram_enabled, updater
    if updater and updater.running:
        updater.stop()
        telegram_enabled = False
        log_message("Telegram bot stopped via /stop command.")
    else:
        log_message("Telegram bot not running to be stopped.")

def telegram_error_handler(update: object, context: CallbackContext) -> None:
    """Log Errors caused by Updates."""
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        chat_info = f"Chat ID: {update.effective_chat.id}"
    elif update and hasattr(update, 'effective_user') and update.effective_user:
        chat_info = f"User ID: {update.effective_user.id}"
    else:
        chat_info = "N/A"

    error_message = f'Telegram error processing update (Update: "{update}", Chat/User Info: "{chat_info}"): {context.error}'
    log_message(error_message)

def initialize_telegram_bot():
    global updater, dp, TELEGRAM_TOKEN, telegram_enabled
    if not TELEGRAM_TOKEN:
        log_message("❌ Cannot start Telegram bot: TELEGRAM_TOKEN is empty.")
        telegram_enabled = False
        return False
    if updater and updater.running:
        log_message("Telegram bot is already running.")
        telegram_enabled = True
        return True
    try:
        log_message("Initializing Telegram bot...")
        updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
        dp = updater.dispatcher
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("status", send_status))
        dp.add_handler(CommandHandler("chatlog", send_chatlog))
        dp.add_handler(CommandHandler("stop", stop_bot_telegram_command))
        dp.add_error_handler(telegram_error_handler)
        updater.start_polling(timeout=20, read_latency=5.0)
        log_message("✅ Telegram bot polling started successfully.")
        telegram_enabled = True
        return True
    except Exception as e:
        log_message(f"❌ Error starting Telegram bot: {e}")
        updater = None
        dp = None
        telegram_enabled = False
        return False

# --- Start Background Threads ---
# Start Growatt Monitor Thread
monitor_thread = threading.Thread(target=monitor_growatt, daemon=True, name="GrowattMonitorThread")
monitor_thread.start()
log_message("Growatt monitor thread started.")

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_downloads, daemon=True, name="CleanupThread")
cleanup_thread.start()
log_message("Download cleanup thread started.")

# --- Flask Routes ---
@app.route("/")
def home():
    global TELEGRAM_TOKEN, last_successful_growatt_update_time
    displayed_token = TELEGRAM_TOKEN
    if TELEGRAM_TOKEN and len(TELEGRAM_TOKEN) > 10:
        displayed_token = TELEGRAM_TOKEN[:5] + "..." + TELEGRAM_TOKEN[-5:]
    return render_template("home.html",
        d=current_data,
        last_growatt_update=last_successful_growatt_update_time,
        plant_id=current_data.get("plant_id", "N/A"),
        user_id=current_data.get("user_id", "N/A"),
        inverter_sn=current_data.get("inverter_sn", "N/A"),
        datalog_sn=current_data.get("datalog_sn", "N/A"),
        telegram_status="Running" if telegram_enabled and updater and updater.running else "Stopped",
        current_telegram_token=displayed_token)

@app.route("/toggle_telegram", methods=["POST"])
def toggle_telegram():
    global telegram_enabled, updater
    action = request.form.get('action')
    if action == 'start' and not telegram_enabled:
        log_message("Attempting to start Telegram bot via Flask.")
        if initialize_telegram_bot():
            telegram_enabled = True; log_message("Telegram bot enabled.")
        else:
            log_message("Failed to enable Telegram bot."); telegram_enabled = False
    elif action == 'stop' and telegram_enabled:
        log_message("Attempting to stop Telegram bot via Flask.")
        if updater and updater.running:
            updater.stop(); telegram_enabled = False; log_message("Telegram bot stopped.")
        else:
            log_message("Telegram bot not running to be stopped.")
    return redirect(url_for('home'))

@app.route("/update_telegram_token", methods=["POST"])
def update_telegram_token():
    global TELEGRAM_TOKEN, telegram_enabled, updater, dp
    new_token = request.form.get('new_telegram_token')
    if not new_token:
        log_message("❌ No new Telegram token provided.")
        return redirect(url_for('home'))
    log_message(f"Attempting to update Telegram token...")
    if updater and updater.running:
        log_message("Stopping existing Telegram bot for token update.")
        try: updater.stop(); time.sleep(1); log_message("Existing Telegram bot stopped.")
        except Exception as e: log_message(f"⚠️ Error stopping existing Telegram bot: {e}")
        finally: updater = None; dp = None
    TELEGRAM_TOKEN = new_token
    log_message(f"Telegram token updated to: {new_token[:5]}...{new_token[-5:]}")
    if initialize_telegram_bot():
        telegram_enabled = True; log_message("Telegram bot restarted successfully with new token.")
    else:
        telegram_enabled = False; log_message("❌ Failed to restart Telegram bot. It remains disabled.")
    return redirect(url_for('home'))

@app.route("/logs")
def logs():
    global last_successful_growatt_update_time
    # Return empty charts since data logging is removed
    return render_template("logs.html", timestamps=[], ac_input=[], ac_output=[],
                           active_power=[], battery_capacity=[],
                           last_growatt_update=last_successful_growatt_update_time)

@app.route("/chatlog")
def chatlog_view():
    return render_template_string("""
        <html><head><title>Growatt Monitor - Chatlog</title><meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes">
        <style>body{font-family:Arial,sans-serif;margin:0;padding:0}nav{background-color:#333;overflow:hidden;position:sticky;top:0;z-index:100}nav ul{list-style-type:none;margin:0;padding:0;display:flex;justify-content:center}nav ul li{padding:14px 20px}nav ul li a{color:white;text-decoration:none;font-size:18px}nav ul li a:hover{background-color:#ddd;color:black}</style></head>
        <body><nav><ul><li><a href="/">Home</a></li><li><a href="/logs">Logs</a></li><li><a href="/chatlog">Chatlog</a></li><li><a href="/console">Console</a></li><li><a href="/details">Details</a></li><li><a href="/battery-chart">Battery Chart</a></li><li><a href="/yt">YouTube</a></li></ul></nav>
        <h1>Chatlog</h1><pre>{{ chat_log }}</pre></body></html>""", chat_log="\n".join(str(cid) for cid in sorted(list(chat_log))))

@app.route("/console")
def console_view():
    return render_template_string("""
        <html><head><title>Console Logs</title><meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes">
        <style>body{font-family:Arial,sans-serif;margin:0;padding:0}nav{background-color:#333;overflow:hidden;position:sticky;top:0;z-index:100}nav ul{list-style-type:none;margin:0;padding:0;display:flex;justify-content:center}nav ul li{padding:14px 20px}nav ul li a{color:white;text-decoration:none;font-size:18px}nav ul li a:hover{background-color:#ddd;color:black}</style></head>
        <body><nav><ul><li><a href="/">Home</a></li><li><a href="/logs">Logs</a></li><li><a href="/chatlog">Chatlog</a></li><li><a href="/console">Console</a></li><li><a href="/details">Details</a></li><li><a href="/battery-chart">Battery Chart</a></li><li><a href="/yt">YouTube</a></li></ul></nav>
        <h2>Console Output (últimos 100 minutos)</h2><pre style="white-space: pre; font-family: monospace; overflow-x: auto;">{{ logs }}</pre>
        <h2>📦 Fetched Growatt Data</h2><pre style="white-space: pre; font-family: monospace; overflow-x: auto;">{{ data }}</pre></body></html>""",
    logs="\n\n".join(m for _, m in console_logs), data=pprint.pformat(fetched_data, indent=2))

@app.route("/battery-chart", methods=["GET", "POST"])
def battery_chart():
    global last_successful_growatt_update_time
    selected_date = request.form.get("date") if request.method == "POST" else get_today_date_utc_minus_5()
    if request.method != "POST": log_message(f"Selected date on GET for battery-chart: {selected_date}")
    growatt_login2()
    battery_payload = {'plantId': PLANT_ID, 'storageSn': STORAGE_SN, 'date': selected_date}
    try:
        battery_response = session.post('https://server.growatt.com/panel/storage/getStorageBatChart', headers=HEADERS, data=battery_payload, timeout=10)
        battery_response.raise_for_status(); battery_data = battery_response.json()
    except requests.exceptions.RequestException as e: log_message(f"❌ Failed to fetch battery data for {selected_date}: {e}"); battery_data = {}
    soc_data = battery_data.get("obj", {}).get("socChart", {}).get("capacity", [])
    if not soc_data: log_message(f"⚠️ No SoC data received for {selected_date}")
    soc_data = soc_data + [None] * (288 - len(soc_data))
    energy_payload = {"date": selected_date, "plantId": PLANT_ID, "storageSn": STORAGE_SN}
    try:
        energy_response = session.post("https://server.growatt.com/panel/storage/getStorageEnergyDayChart", headers=HEADERS, data=energy_payload, timeout=10)
        energy_response.raise_for_status(); energy_data = energy_response.json()
    except requests.exceptions.RequestException as e: log_message(f"❌ Failed to fetch energy chart data for {selected_date}: {e}"); energy_data = {}
    energy_obj = energy_data.get("obj", {}).get("charts", {}); energy_titles = energy_data.get("titles", [])
    def prepare_series(dl, n, c):
        cd = [float(x) if (isinstance(x,(int,float)) or (isinstance(x,str) and x.replace('.','',1).isdigit())) else None for x in dl]
        return {"name":n,"data":cd,"color":c,"fillOpacity":0.2,"lineWidth":1} if any(x is not None for x in cd) else None
    energy_series = [s for s in [
        prepare_series(energy_obj.get("ppv"), "Photovoltaic Output", "#FFEB3B"),
        prepare_series(energy_obj.get("userLoad"), "Load Consumption", "#9C27B0"),
        prepare_series(energy_obj.get("pacToUser"), "Imported from Grid", "#00BCD4"),
    ] if s and s['name'] != 'Exported to Grid']
    if not any(s and s['data'] for s in energy_series): log_message(f"⚠️ No usable energy chart data for {selected_date}")
    for s in energy_series: s["data"] = (s["data"] if s and s["data"] else []) + [None]*(288-len(s["data"] if s and s["data"] else []))
    return render_template("battery-chart.html", selected_date=selected_date, soc_data=soc_data,
                           raw_json=battery_data, energy_titles=energy_titles, energy_series=energy_series,
                           last_growatt_update=last_successful_growatt_update_time)

@app.route("/details", methods=["GET", "POST"])
def details():
    global last_successful_growatt_update_time
    selected_date = request.form.get("date") if request.method == "POST" else get_today_date_utc_minus_5()
    if request.method != "POST":
        log_message(f"Selected date on GET for details page: {selected_date}")

    growatt_login2()

    NEW_API_PLANT_ID = '2817170'
    NEW_API_STORAGE_SN = 'BNG7CH806N'
    DEVICES_DAY_CHART_URL = "https://server.growatt.com/energy/compare/getDevicesDayChart"

    def prepare_series(dl, n, c):
        if not isinstance(dl, list):
            log_message(f"‼️ Warning: Input data for series '{n}' is not a list. Received type: {type(dl)}. Treating as empty.")
            dl = []

        cd = [float(x) if (isinstance(x, (int, float)) or (isinstance(x, str) and x.replace('.', '', 1).isdigit())) else None for x in dl]

        if any(x is not None for x in cd):
            return {"name": n, "data": cd, "color": c, "fillOpacity": 0.2, "lineWidth": 1}
        return None

    volt_series_data = []
    raw_json_volts_response = {}
    volt_request_jsonData = [{"type": "storage", "sn": NEW_API_STORAGE_SN, "params": "vGrid,outPutVolt"}]
    volt_payload = {'plantId': NEW_API_PLANT_ID, 'date': selected_date, 'jsonData': json.dumps(volt_request_jsonData)}

    try:
        response_volts = session.post(DEVICES_DAY_CHART_URL, headers=HEADERS, data=volt_payload, timeout=10)
        response_volts.raise_for_status()
        raw_json_volts_response = response_volts.json()

        vGrid_values = []
        outPutVolt_values = []

        obj_list_volts = raw_json_volts_response.get("obj")
        if isinstance(obj_list_volts, list) and len(obj_list_volts) > 0:
            first_item_volts = obj_list_volts[0]
            if isinstance(first_item_volts, dict):
                datas_dict_volts = first_item_volts.get("datas")
                if isinstance(datas_dict_volts, dict):
                    vGrid_values = datas_dict_volts.get("vGrid", [])
                    outPutVolt_values = datas_dict_volts.get("outPutVolt", [])
                else:
                    log_message(f"⚠️ 'datas' key for volts is not a dict or missing. Response: {raw_json_volts_response}")
            else:
                log_message(f"⚠️ First item in 'obj' list for volts is not a dict. Response: {raw_json_volts_response}")
        else:
            log_message(f"⚠️ 'obj' key for volts is not a list, is empty, or missing. Response: {raw_json_volts_response}")

        prepared_series_list_volts = []
        series_vgrid = prepare_series(vGrid_values, "Grid Voltage (V)", "#FF5733")
        if series_vgrid: prepared_series_list_volts.append(series_vgrid)
        series_outputvolt = prepare_series(outPutVolt_values, "Output Voltage (V)", "#33FF57")
        if series_outputvolt: prepared_series_list_volts.append(series_outputvolt)
        volt_series_data = prepared_series_list_volts

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Failed to fetch voltage data for {selected_date}: {e}")
    except Exception as e:
        log_message(f"❌ Unexpected error processing voltage data for {selected_date}: {e}")


    amp_series_data = []
    raw_json_amps_response = {}
    amp_request_jsonData = [{"type": "storage", "sn": NEW_API_STORAGE_SN, "params": "ppv"}]
    amp_payload = {'plantId': NEW_API_PLANT_ID, 'date': selected_date, 'jsonData': json.dumps(amp_request_jsonData)}

    try:
        response_amps = session.post(DEVICES_DAY_CHART_URL, headers=HEADERS, data=amp_payload, timeout=10)
        response_amps.raise_for_status()
        raw_json_amps_response = response_amps.json()

        ppv_values = []

        obj_list_amps = raw_json_amps_response.get("obj")
        if isinstance(obj_list_amps, list) and len(obj_list_amps) > 0:
            first_item_amps = obj_list_amps[0]
            if isinstance(first_item_amps, dict):
                datas_dict_amps = first_item_amps.get("datas")
                if isinstance(datas_dict_amps, dict):
                    ppv_values = datas_dict_amps.get("ppv", [])
                else:
                    log_message(f"⚠️ 'datas' key for amps is not a dict or missing. Response: {raw_json_amps_response}")
            else:
                log_message(f"⚠️ First item in 'obj' list for amps is not a dict. Response: {raw_json_amps_response}")
        else:
            log_message(f"⚠️ 'obj' key for amps is not a list, is empty, or missing. Response: {raw_json_amps_response}")

        prepared_series_list_amps = []
        series_ppv = prepare_series(ppv_values, "PV Current (A)", "#3357FF")
        if series_ppv: prepared_series_list_amps.append(series_ppv)
        amp_series_data = prepared_series_list_amps

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Failed to fetch amperage data for {selected_date}: {e}")
    except Exception as e:
        log_message(f"❌ Unexpected error processing amperage data for {selected_date}: {e}")

    for series_list_to_pad in [volt_series_data, amp_series_data]:
        for s_object in series_list_to_pad:
            if s_object and "data" in s_object:
                current_data_list = s_object["data"] if s_object["data"] else []
                s_object["data"] = current_data_list + [None] * (288 - len(current_data_list))

    return render_template("details.html",
                           selected_date=selected_date,
                           chart1_data_series=volt_series_data,
                           chart2_data_series=amp_series_data,
                           raw_json_chart1=raw_json_volts_response,
                           raw_json_chart2=raw_json_amps_response,
                           last_growatt_update=last_successful_growatt_update_time)

# --- YouTube Downloader Routes ---

@app.route('/yt')
def yt_downloader_page():
    """Serve the YouTube downloader HTML page"""
    return render_template_string(YT_DOWNLOADER_HTML)

@app.route('/api/yt/search')
def yt_search():
    """Search YouTube videos"""
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    ydl_opts = {
        'quiet': True,
        'extract_flat': 'in_playlist',
        'playlistend': 15,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            search_url = f"ytsearch15:{query}"
            info = ydl.extract_info(search_url, download=False)
            entries = info.get('entries', [])
            results = []
            for entry in entries:
                results.append({
                    'id': entry.get('id'),
                    'title': entry.get('title'),
                    'webpage_url': entry.get('webpage_url') or f"https://youtube.com/watch?v={entry.get('id')}",
                    'thumbnail': entry.get('thumbnail'),
                    'duration': entry.get('duration_string'),
                    'author': entry.get('uploader', 'Unknown')
                })
            return jsonify({'videos': results})
        except Exception as e:
            log_message(f"❌ YouTube search error: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/yt/info')
def yt_video_info():
    """Get info for a single video"""
    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    ydl_opts = {'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                'id': info.get('id'),
                'title': info.get('title'),
                'webpage_url': url,
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration_string'),
                'author': info.get('uploader', 'Unknown')
            })
        except Exception as e:
            log_message(f"❌ YouTube info error: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/yt/download')
def yt_download():
    """Download video in 720p MP4 or best available"""
    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    # Format selector: best video up to 720p MP4 + best audio, fallback to best MP4
    ydl_opts = {
        'format': '(bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best)',
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s_%(id)s.%(ext)s'),
        'quiet': True,
        'merge_output_format': 'mp4',
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            log_message(f"📥 Downloading: {url}")
            info = ydl.extract_info(url, download=True)
            
            # Get the actual filename
            filename = ydl.prepare_filename(info)
            
            # Handle if format changed extension
            if not os.path.exists(filename):
                for f in os.listdir(DOWNLOAD_FOLDER):
                    if info.get('id') in f and f.endswith('.mp4'):
                        filename = os.path.join(DOWNLOAD_FOLDER, f)
                        break
            
            if os.path.exists(filename):
                log_message(f"✅ Download complete: {info.get('title')}")
                return send_file(
                    filename, 
                    as_attachment=True,
                    download_name=f"{info.get('title')}.mp4"
                )
            else:
                return jsonify({'error': 'File not found after download'}), 500
                
        except Exception as e:
            log_message(f"❌ YouTube download error: {e}")
            return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    log_message("Starting Flask development server.")
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)