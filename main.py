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

# --- File for saving data ---
data_file = "saved_data.json"

# Ensure the file exists and is initialized as an empty JSON array
if not os.path.exists(data_file) or os.path.getsize(data_file) == 0:
    with open(data_file, "w") as f:
        f.write("[]")  # Initialize with an empty JSON array
    print(f"Initialized empty data file: {data_file}")

# --- Credentials ---
username1 = "vospina"
password1 = "Vospina.2025"

# --- Telegram Config ---
TELEGRAM_TOKEN = "7653969082:AAGGuY6-sZz0KbVDTa0zfNanMF4MH1vP_oo" # <--- YOUR CURRENT TOKEN
CHAT_IDS = ["5715745951"]  # Only sends messages to 'sergiojim' chat ID
chat_log = set()

# Global variable to control Telegram bot state
telegram_enabled = False
updater = None  # Global reference for the Updater object
dp = None       # Global reference for the Dispatcher object

# --- Flask App ---
app = Flask(__name__)

GROWATT_USERNAME = "vospina"
PASSWORD_CRC = "0c4107c238d57d475d4660b07b2f043e"
STORAGE_SN = "BNG7CH806N"
PLANT_ID = "2817170" # Use this specific Plant ID as provided

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
last_processed_time = "Never" # When our Flask app last processed data
# NEW: This will store the actual logger update time from Growatt server
last_logger_update_time_from_growatt = "N/A - Not yet fetched" 
console_logs = []

def log_message(message):
    timestamped = f"{(datetime.now() - timedelta(hours=5)).strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now = time.time()
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 300]


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

fetched_data = {}

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

def save_data_to_file(data):
    try:
        existing_data = []
        if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
            with open(data_file, "r") as f:
                try:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        log_message(f"⚠️ Warning: {data_file} did not contain a JSON list. Attempting to convert.")
                        existing_data = [existing_data]
                except json.JSONDecodeError:
                    f.seek(0)
                    lines = f.readlines()
                    existing_data = []
                    for line in lines:
                        stripped_line = line.strip()
                        if stripped_line:
                            try:
                                existing_data.append(json.loads(stripped_line))
                            except json.JSONDecodeError as e:
                                log_message(f"❌ Error decoding existing JSON line in {data_file}: {stripped_line} - {e}")
        
        existing_data.append(data)
        existing_data = existing_data[-1200:]

        with open(data_file, "w") as f:
            json.dump(existing_data, f, indent=None, separators=(',', ':'))

        log_message("✅ Saved data to file as a JSON array.")
    except Exception as e:
        log_message(f"❌ Error saving data to file: {e}")

# NEW: Function to fetch the logger's last update time
def get_logger_last_update_from_growatt(plant_id_val):
    global last_logger_update_time_from_growatt # Allow updating the global variable
    log_message(f"Fetching logger last update time for Plant ID: {plant_id_val}")
    url = "https://server.growatt.com/panel/getDevicesByPlantList"
    payload = {
        'currPage': 1,
        'plantId': plant_id_val # Use the dynamically fetched plant ID
    }
    try:
        response = session.post(url, headers=HEADERS, data=payload, timeout=10)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        data = response.json()
        
        # Navigate the JSON response to find lastUpdateTime
        # {"result":1,"obj":{"datas":[{"lastUpdateTime":"2025-05-22 21:11:05"}]}}}
        if data.get("result") == 1 and data.get("obj") and data["obj"].get("datas"):
            # Assuming the first device in the list is the relevant one
            logger_data = data["obj"]["datas"][0]
            if "lastUpdateTime" in logger_data:
                last_update_time = logger_data["lastUpdateTime"]
                log_message(f"Received logger last update time: {last_update_time}")
                last_logger_update_time_from_growatt = last_update_time # Update global variable
                return last_update_time
            else:
                log_message("⚠️ 'lastUpdateTime' not found in Growatt devices list response.")
        else:
            log_message(f"⚠️ Unexpected Growatt devices list response structure or result: {data}")
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Error fetching logger last update time from Growatt: {e}")
    except json.JSONDecodeError as e:
        log_message(f"❌ Error decoding JSON from Growatt devices list: {e}")
    except Exception as e:
        log_message(f"❌ An unexpected error occurred while fetching logger update time: {e}")
    
    # If anything fails, set to N/A or keep previous value
    # last_logger_update_time_from_growatt is updated only on success, else keeps old value.
    # We might want to explicitly set to 'N/A - Error' if it fails.
    if last_logger_update_time_from_growatt == "N/A - Not yet fetched" or "Error" not in last_logger_update_time_from_growatt:
        last_logger_update_time_from_growatt = "N/A - Fetch Failed"
    return None # Return None if unable to fetch

def monitor_growatt():
    global last_processed_time, last_logger_update_time_from_growatt
    threshold = 80
    sent_lights_off = False
    sent_lights_on = False

    loop_counter = 0

    user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None

    while True:
        try:
            # Always attempt to (re)login and get IDs if they are missing
            if user_id is None or plant_id is None or inverter_sn is None or datalog_sn is None:
                log_message("Attempting to acquire Growatt IDs (re-login or initial login).")
                user_id, plant_id, inverter_sn, datalog_sn = login_growatt()
                if user_id is None:
                    log_message("Growatt login/ID fetching failed. Retrying in 60 seconds.")
                    time.sleep(60)
                    continue

            # Fetch detailed inverter data
            data = api.storage_detail(inverter_sn)
            log_message(f"Growatt API storage_detail data: {data}")

            # Fetch the actual logger's last update time from the server
            get_logger_last_update_from_growatt(plant_id) # Pass plant_id to the function

            ac_input_v = data.get("vGrid", "N/A")
            ac_input_f = data.get("freqGrid", "N/A")
            ac_output_v = data.get("outPutVolt", "N/A")
            ac_output_f = data.get("freqOutPut", "N/A")
            load_w = data.get("activePower", "N/A")
            battery_pct = data.get("capacity", "N/A")

            current_data.update({
                "ac_input_voltage": ac_input_v,
                "ac_input_frequency": ac_input_f,
                "ac_output_voltage": ac_output_v,
                "ac_output_frequency": ac_output_f,
                "load_power": load_w,
                "battery_capacity": battery_pct,
                "user_id": user_id,
                "plant_id": plant_id,
                "inverter_sn": inverter_sn,
                "datalog_sn": datalog_sn
            })

            last_processed_time = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
            log_message(f"Updated current_data and last_processed_time.")

            loop_counter += 1
            if loop_counter >= 7:
                data_to_save = {
                    # Use the logger's last update time for data saving if available
                    "timestamp": last_logger_update_time_from_growatt if "N/A" not in last_logger_update_time_from_growatt else last_processed_time, 
                    "vGrid": ac_input_v,
                    "outPutVolt": ac_output_v,
                    "activePower": load_w,
                    "capacity": battery_pct,
                    "freqOutPut": ac_output_f
                }
                save_data_to_file(data_to_save)
                loop_counter = 0

            if telegram_enabled:
                if ac_input_v != "N/A":
                    try:
                        current_ac_input_v = float(ac_input_v)
                    except ValueError:
                        current_ac_input_v = 0.0

                    if current_ac_input_v < threshold and not sent_lights_off:
                        time.sleep(110)
                        data_confirm = api.storage_detail(inverter_sn)
                        ac_input_v_confirm = data_confirm.get("vGrid", "0")
                        try:
                            current_ac_input_v_confirm = float(ac_input_v_confirm)
                        except ValueError:
                            current_ac_input_v_confirm = 0.0

                        if current_ac_input_v_confirm < threshold:
                            msg = f"""🔴🔴¡Se fue la luz en Acacías!🔴🔴
        🕒 Hora del logger: {last_logger_update_time_from_growatt}
Nivel de batería      : {battery_pct} %
Voltaje de la red     : {current_ac_input_v_confirm} V / {ac_input_f} Hz
Voltaje del inversor: {ac_output_v} V / {ac_output_f} Hz
Consumo actual     : {load_w} W"""
                            send_telegram_message(msg)
                            sent_lights_off = True
                            sent_lights_on = False

                    elif current_ac_input_v >= threshold and not sent_lights_on:
                        time.sleep(110)
                        data_confirm = api.storage_detail(inverter_sn)
                        ac_input_v_confirm = data_confirm.get("vGrid", "0")
                        try:
                            current_ac_input_v_confirm = float(ac_input_v_confirm)
                        except ValueError:
                            current_ac_input_v_confirm = 0.0

                        if current_ac_input_v_confirm >= threshold:
                            msg = f"""✅✅¡Llegó la luz en Acacías!✅✅
        🕒 Hora del logger: {last_logger_update_time_from_growatt}
Nivel de batería      : {battery_pct} %
Voltaje de la red     : {current_ac_input_v_confirm} V / {ac_input_f} Hz
Voltaje del inversor: {ac_output_v} V / {ac_output_f} Hz
Consumo actual     : {load_w} W"""
                            send_telegram_message(msg)
                            sent_lights_on = True
                            sent_lights_off = False

        except Exception as e_inner:
            log_message(f"⚠️ Error during Growatt data fetch or processing: {e_inner}")
            # Reset IDs to force re-login attempt in next loop
            user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None 

        time.sleep(40)

# Telegram Handlers (unchanged)
def start(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    update.message.reply_text("¡Bienvenido al monitor Growatt! Usa /status para ver el estado del inversor.")

def send_status(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)

    timestamp = (datetime.now() - timedelta(hours=5)).strftime("%H:%M:%S")

    msg = f"""⚡ /status Estado del Inversor /stop⚡
        🕒 Hora del logger: {last_logger_update_time_from_growatt} 
Voltaje Red          : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje Inversor   : {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo             : {current_data.get('load_power', 'N/A')} W
Batería                 : {current_data.get('battery_capacity', 'N/A')}%
"""
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

def initialize_telegram_bot():
    global updater, dp, TELEGRAM_TOKEN, telegram_enabled
    if not TELEGRAM_TOKEN:
        log_message("❌ Cannot start Telegram bot: TELEGRAM_TOKEN is empty.")
        return False

    if updater and updater.running:
        log_message("Telegram bot is already running. No re-initialization needed unless token changed.")
        return True

    try:
        log_message("Initializing Telegram bot...")
        updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
        dp = updater.dispatcher
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("status", send_status))
        dp.add_handler(CommandHandler("chatlog", send_chatlog))
        dp.add_handler(CommandHandler("stop", stop_bot_telegram_command))
        updater.start_polling()
        log_message("Telegram bot polling started.")
        return True
    except Exception as e:
        log_message(f"❌ Error starting Telegram bot (check token): {e}")
        updater = None
        dp = None
        telegram_enabled = False
        return False

monitor_thread = threading.Thread(target=monitor_growatt, daemon=True)
monitor_thread.start()

# --- Flask Routes ---
@app.route("/")
def home():
    global TELEGRAM_TOKEN, last_logger_update_time_from_growatt
    displayed_token = TELEGRAM_TOKEN
    if TELEGRAM_TOKEN and len(TELEGRAM_TOKEN) > 10:
        displayed_token = TELEGRAM_TOKEN[:5] + "..." + TELEGRAM_TOKEN[-5:]

    return render_template("home.html",
        d=current_data,
        last_growatt_update=last_logger_update_time_from_growatt, # NOW using logger's update time
        plant_id=current_data.get("plant_id", "N/A"),
        user_id=current_data.get("user_id", "N/A"),
        inverter_sn=current_data.get("inverter_sn", "N/A"),
        datalog_sn=current_data.get("datalog_sn", "N/A"),
        telegram_status="Running" if telegram_enabled and updater and updater.running else "Stopped",
        current_telegram_token=displayed_token
        )

@app.route("/toggle_telegram", methods=["POST"])
def toggle_telegram():
    global telegram_enabled, updater
    action = request.form.get('action')

    if action == 'start' and not telegram_enabled:
        log_message("Attempting to start Telegram bot via Flask.")
        if initialize_telegram_bot():
            telegram_enabled = True
            log_message("Telegram bot enabled.")
        else:
            log_message("Failed to enable Telegram bot (check logs for token error).")
            telegram_enabled = False
    elif action == 'stop' and telegram_enabled:
        log_message("Attempting to stop Telegram bot via Flask.")
        if updater and updater.running:
            updater.stop()
            telegram_enabled = False
            log_message("Telegram bot stopped.")
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
        try:
            updater.stop()
            time.sleep(1)
            log_message("Existing Telegram bot stopped.")
        except Exception as e:
            log_message(f"⚠️ Error stopping existing Telegram bot: {e}")
        finally:
            updater = None
            dp = None

    TELEGRAM_TOKEN = new_token
    log_message(f"Telegram token updated to: {new_token[:5]}...{new_token[-5:]}") 

    if initialize_telegram_bot():
        telegram_enabled = True
        log_message("Telegram bot restarted successfully with new token.")
    else:
        telegram_enabled = False
        log_message("❌ Failed to restart Telegram bot with new token. It remains disabled. Check logs for details.")

    return redirect(url_for('home'))


@app.route("/logs")
def charts_view():
    parsed_data = []
    if os.path.exists(data_file) and os.path.getsize(data_file) > 0: 
        try:
            with open(data_file, "r") as file:
                parsed_data = json.load(file)
            if not isinstance(parsed_data, list):
                log_message(f"❌ Data file {data_file} does not contain a JSON list. Resetting.")
                parsed_data = []
        except json.JSONDecodeError as e:
            log_message(f"❌ Error decoding JSON from {data_file}: {e}. File might be corrupted.")
            parsed_data = []
        except Exception as e:
            log_message(f"❌ General error reading data for charts from {data_file}: {e}")
            parsed_data = []
    else:
        log_message(f"⚠️ Data file not found or empty: {data_file}. Charts will be empty.")
        if not os.path.exists(data_file) or os.path.getsize(data_file) == 0:
            try:
                with open(data_file, "w") as f:
                    f.write("[]")
                log_message(f"Initialized empty data file: {data_file}")
            except Exception as e:
                log_message(f"❌ Error initializing empty data file: {e}")

    processed_data = []
    for entry in parsed_data:
        if 'timestamp' in entry and isinstance(entry['timestamp'], str):
            try:
                entry['dt_timestamp'] = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
                processed_data.append(entry)
            except ValueError:
                log_message(f"Skipping entry with invalid timestamp format: {entry.get('timestamp')}")
        else:
            log_message(f"Skipping entry with missing or non-string timestamp: {entry}")

    processed_data.sort(key=lambda x: x['dt_timestamp'])

    max_duration_hours_to_send = 96
    
    if processed_data:
        reference_time = processed_data[-1]['dt_timestamp']
    else:
        reference_time = datetime.now() 

    cutoff_time = reference_time - timedelta(hours=max_duration_hours_to_send)

    filtered_data_for_frontend = [
        entry for entry in processed_data
        if entry['dt_timestamp'] >= cutoff_time
    ]

    timestamps = [entry['timestamp'] for entry in filtered_data_for_frontend]
    ac_input = [float(entry['vGrid']) for entry in filtered_data_for_frontend]
    ac_output = [float(entry['outPutVolt']) for entry in filtered_data_for_frontend]
    active_power = [int(entry['activePower']) for entry in filtered_data_for_frontend]
    battery_capacity = [int(entry['capacity']) for entry in filtered_data_for_frontend]

    return render_template("logs.html",
        timestamps=timestamps,
        ac_input=ac_input,
        ac_output=ac_output,
        active_power=active_power,
        battery_capacity=battery_capacity)     

@app.route("/chatlog")
def chatlog_view():
    return render_template_string("""
        <html>
        <head>
            <title>Growatt Monitor - Chatlog</title>
            <meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes">
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                }
                nav {
                    background-color: #333;
                    overflow: hidden;
                    position: sticky;
                    top: 0;
                    z-index: 100;
                }
                nav ul {
                    list-style-type: none;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                }
                nav ul li {
                    padding: 14px 20px;
                }
                nav ul li a {
                    color: white;
                    text-decoration: none;
                    font-size: 18px;
                }
                nav ul li a:hover {
                    background-color: #ddd;
                    color: black;
                }
            </style>
        </head>
        <body>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a></li>
                    <li><a href="/chatlog">Chatlog</a></li>
                    <li><a href="/console">Console</a></li>
                    <li><a href="/details">Details</a></li>
                    <li><a href="/battery-chart">Battery Chart</a></li>
                </ul>
            </nav>
            <h1>Chatlog</h1>
            <pre>{{ chat_log }}</pre>
        </body>
        </html>
    """, chat_log="\n".join(str(cid) for cid in sorted(list(chat_log))))

@app.route("/console")
def console_view():
    return render_template_string("""
        <html>
        <head>
            <title>Console Logs</title>
            <meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes">
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                }
                nav {
                    background-color: #333;
                    overflow: hidden;
                    position: sticky;
                    top: 0;
                    z-index: 100;
                }
                nav ul {
                    list-style-type: none;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                }
                nav ul li {
                    padding: 14px 20px;
                }
                nav ul li a {
                    color: white;
                    text-decoration: none;
                    font-size: 18px;
                }
                nav ul li a:hover {
                    background-color: #ddd;
                    color: black;
                }
            </style>
        </head>
        <body>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a></li>
                    <li><a href="/chatlog">Chatlog</a></li>
                    <li><a href="/console">Console</a></li>
                    <li><a href="/details">Details</a></li>
                    <li><a href="/battery-chart">Battery Chart</a></li>
                </ul>
            </nav>
            <h2>Console Output (últimos 5 minutos)</h2>
            <pre style="white-space: pre; font-family: monospace; overflow-x: auto;">{{ logs }}</pre>

            <h2>📦 Fetched Growatt Data</h2>
            <pre style="white-space: pre; font-family: monospace; overflow-x: auto;">{{ data }}</pre>
        </body>
        </html>
    """, 
    logs="\n\n".join(m for _, m in console_logs),
    data=pprint.pformat(fetched_data, indent=2))

@app.route("/battery-chart", methods=["GET", "POST"])
def battery_chart():
    if request.method == "POST":
        selected_date = request.form.get("date")
    else:
        selected_date = get_today_date_utc_minus_5()
        print(f"Selected date on GET: {selected_date}")

    growatt_login2()

    battery_payload = {
        'plantId': PLANT_ID,
        'storageSn': STORAGE_SN,
        'date': selected_date
    }

    try:
        battery_response = session.post(
            'https://server.growatt.com/panel/storage/getStorageBatChart',
            headers=HEADERS,
            data=battery_payload,
            timeout=10
        )
        battery_response.raise_for_status()
        battery_data = battery_response.json()
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Failed to fetch battery data for {selected_date}: {e}")
        battery_data = {}

    soc_data = battery_data.get("obj", {}).get("socChart", {}).get("capacity", [])
    if not soc_data:
        log_message(f"⚠️ No SoC data received for {selected_date}")
    soc_data = soc_data + [None] * (288 - len(soc_data))

    energy_payload = {
        "date": selected_date,
        "plantId": PLANT_ID,
        "storageSn": STORAGE_SN
    }

    try:
        energy_response = session.post(
            "https://server.growatt.com/panel/storage/getStorageEnergyDayChart",
            headers=HEADERS,
            data=energy_payload,
            timeout=10
        )
        energy_response.raise_for_status()
        energy_data = energy_response.json()
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Failed to fetch energy chart data for {selected_date}: {e}")
        energy_data = {}

    energy_obj = energy_data.get("obj", {}).get("charts", {})
    energy_titles = energy_data.get("titles", [])

    def prepare_series(data_list, name, color):
        if not data_list or not isinstance(data_list, list) or not data_list:
            return None
        return {"name": name, "data": data_list, "color": color, "fillOpacity": 0.2, "lineWidth": 1}

    energy_series = [
        prepare_series(energy_obj.get("ppv"), "Photovoltaic Output", "#FFEB3B"),
        prepare_series(energy_obj.get("userLoad"), "Load Consumption", "#9C27B0"),
        prepare_series(energy_obj.get("pacToUser"), "Imported from Grid", "#00BCD4"),
    ]
    energy_series = [s for s in energy_series if s and s['name'] != 'Exported to Grid']

    if not any(series and series['data'] for series in energy_series):
        log_message(f"⚠️ No usable energy chart data received for {selected_date}")

    for series in energy_series:
        if series and series["data"]:
            series["data"] = series["data"] + [None] * (288 - len(series["data"]))
        elif series:
            series["data"] = [None] * 288

    return render_template(
        "battery-chart.html",
        selected_date=selected_date,
        soc_data=soc_data,
        raw_json=battery_data,
        energy_titles=energy_titles,
        energy_series=energy_series
    )

@app.route('/dn')
def download_logs():
    try:
        return send_file(data_file, as_attachment=True, download_name="saved_data.json", mimetype="application/json")
    except Exception as e:
        log_message(f"❌ Error downloading file: {e}")
        return f"❌ Error downloading file: {e}", 500

        
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
