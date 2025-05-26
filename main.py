from flask import Flask, render_template, render_template_string, jsonify, request, send_file, redirect, url_for
import threading
import pprint
import json
import os
import time
import requests
from datetime import datetime, timedelta
from growattServer import GrowattApi # Assuming this library is correctly installed
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
username1 = "vospina" # Replace with your actual Growatt username
password1 = "Vospina.2025" # Replace with your actual Growatt password

# --- Telegram Config ---
TELEGRAM_TOKEN = "7653969082:AAGGuY6-sZz0KbVDTa0zfNanMF4MH1vP_oo" # YOUR ACTUAL TOKEN
CHAT_IDS = ["5715745951"]  # Your desired chat ID(s)
chat_log = set()

# Global variable to control Telegram bot state
telegram_enabled = False
updater = None  # Global reference for the Updater object
dp = None       # Global reference for the Dispatcher object

# --- Flask App ---
app = Flask(__name__)

# These seem to be for a secondary way of interacting with Growatt, keep if needed
GROWATT_USERNAME = "vospina" # Replace if different from username1
PASSWORD_CRC = "0c4107c238d57d475d4660b07b2f043e" # If password for GROWATT_USERNAME changes, this CRC needs to be updated
STORAGE_SN = "BNG7CH806N" # Your specific storage SN
PLANT_ID = "2817170" # Your specific Plant ID for battery-chart, if different from dynamically fetched one

HEADERS = {
    'User-Agent': 'Mozilla/5.5',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest'
}

session = requests.Session()

def growatt_login2():
    # This login seems to be for the /battery-chart endpoint specifically
    data = {
        'account': GROWATT_USERNAME,
        'password': '', # Password sent as CRC
        'validateCode': '',
        'isReadPact': '0',
        'passwordCrc': PASSWORD_CRC
    }
    try:
        response = session.post('https://server.growatt.com/login', headers=HEADERS, data=data, timeout=10)
        response.raise_for_status()
        log_message("growatt_login2: Secondary login successful or session active.")
    except requests.exceptions.RequestException as e:
        log_message(f"growatt_login2: Secondary login failed: {e}")


def get_today_date_utc_minus_5():
    # Colombia is UTC-5
    now = datetime.utcnow() - timedelta(hours=5)
    return now.strftime('%Y-%m-%d')

# Growatt API library instance
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})

# --- Shared Data ---
current_data = {}
last_processed_time = "Never" # When Flask app last processed data from monitor_growatt
last_logger_update_time_from_growatt = "N/A - Not yet fetched" # Actual logger update time from Growatt
console_logs = []

def log_message(message):
    timestamped = f"{(datetime.now() - timedelta(hours=5)).strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now_ts = time.time() # Renamed to avoid conflict with datetime.now
    # Keep logs for the last 5 minutes (300 seconds)
    console_logs[:] = [(t, m) for t, m in console_logs if now_ts - t < 300]

# --- Data Conversion Helper Functions ---
def safe_float(value, default_value=None):
    if value is None or value == "N/A":
        return default_value
    try:
        return float(value)
    except (ValueError, TypeError):
        # log_message(f"Warning: Could not convert '{value}' to float, using default.")
        return default_value

def safe_int(value, default_value=None):
    if value is None or value == "N/A":
        return default_value
    try:
        return int(float(value)) # Attempt float first for strings like "123.0"
    except (ValueError, TypeError):
        # log_message(f"Warning: Could not convert '{value}' to int, using default.")
        return default_value

# --- Telegram Integration ---
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
        if not telegram_enabled:
            log_message(f"Telegram not enabled. Message not sent: {message[:100]}...") # Log snippet
        elif not (updater and updater.running):
            log_message(f"Telegram updater not running. Message not sent: {message[:100]}...")


fetched_data = {} # For storing raw API responses for /console display

def login_growatt():
    log_message("🔄 Attempting Growatt login (main API)...")
    try:
        login_response = api.login(username1, password1)
        fetched_data['login_response'] = login_response # Store for debugging
        user = login_response.get('user', {})
        user_id = user.get('id')
        # Storing more details for potential use or debugging
        fetched_data['user_id'] = user_id
        fetched_data['cpower_token'] = user.get('cpowerToken')
        fetched_data['cpower_auth'] = user.get('cpowerAuth')
        fetched_data['account_name'] = user.get('accountName')
        fetched_data['email'] = user.get('email')
        fetched_data['last_login_time'] = user.get('lastLoginTime')
        fetched_data['user_area'] = user.get('area')
        log_message("✅ Main API Login successful!")
    except Exception as e:
        log_message(f"❌ Main API Login failed: {e}")
        return None, None, None, None

    try:
        plant_info = api.plant_list(user_id)
        fetched_data['plant_info'] = plant_info
        # Assuming at least one plant exists and is the one we want
        if not plant_info.get('data') or not plant_info['data'][0]:
            log_message("❌ No plant data found in API response.")
            return None, None, None, None
        plant_data = plant_info['data'][0]
        plant_id_val = plant_data['plantId'] # Renamed to avoid conflict with constant
        fetched_data['plant_id'] = plant_id_val
        fetched_data['plant_name'] = plant_data.get('plantName')
        fetched_data['plant_total_data'] = plant_info.get('totalData', {})
    except Exception as e:
        log_message(f"❌ Failed to retrieve plant info: {e}")
        return user_id, None, None, None # Return user_id if login was ok

    try:
        inverter_info_list = api.inverter_list(plant_id_val) # Use list suffix if it returns a list
        fetched_data['inverter_info_list'] = inverter_info_list
        if not inverter_info_list or not isinstance(inverter_info_list, list) or len(inverter_info_list) == 0:
            log_message("❌ No inverter data found or invalid format.")
            return user_id, plant_id_val, None, None
        inverter_data = inverter_info_list[0] # Assuming first inverter
        inverter_sn = inverter_data['deviceSn']
        datalog_sn = inverter_data.get('datalogSn', 'N/A')
        fetched_data['inverter_sn'] = inverter_sn
        fetched_data['datalog_sn'] = datalog_sn
        # Storing more inverter details
        fetched_data['inverter_alias'] = inverter_data.get('deviceAilas') # Typo in original 'deviceAilas' retained if API uses it
        fetched_data['inverter_capacity'] = inverter_data.get('capacity')
        fetched_data['inverter_energy'] = inverter_data.get('energy')
        fetched_data['inverter_active_power'] = inverter_data.get('activePower')
        fetched_data['inverter_apparent_power'] = inverter_data.get('apparentPower')
        fetched_data['inverter_status'] = inverter_data.get('deviceStatus')
    except Exception as e:
        log_message(f"❌ Failed to retrieve inverter info: {e}")
        return user_id, plant_id_val, None, None

    # Optionally fetch initial storage detail here for fetched_data, but monitor_growatt will do it too
    try:
        storage_detail = api.storage_detail(inverter_sn)
        fetched_data['storage_detail_initial'] = storage_detail
    except Exception as e:
        log_message(f"❌ Failed to retrieve initial storage detail: {e}")
        # Not critical for login success itself, so don't return None here

    log_message(f"🌿 User ID: {user_id}")
    log_message(f"🌿 Plant ID (dynamic): {plant_id_val}")
    log_message(f"🌿 Inverter SN: {inverter_sn}")
    log_message(f"🌿 Datalogger SN: {datalog_sn}")

    return user_id, plant_id_val, inverter_sn, datalog_sn


def save_data_to_file(data_to_save_val): # Renamed parameter
    try:
        existing_data = []
        if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
            with open(data_file, "r") as f:
                try:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        log_message(f"⚠️ Warning: {data_file} did not contain a JSON list. Re-initializing.")
                        existing_data = [] # If not a list, better to start fresh or handle carefully
                except json.JSONDecodeError:
                    log_message(f"⚠️ {data_file} is corrupted or not valid JSON. Attempting line-by-line recovery.")
                    f.seek(0)
                    lines = f.readlines()
                    existing_data = []
                    for line in lines:
                        stripped_line = line.strip()
                        if stripped_line:
                            try:
                                existing_data.append(json.loads(stripped_line))
                            except json.JSONDecodeError as e_line:
                                log_message(f"❌ Error decoding existing JSON line: '{stripped_line[:50]}...' - {e_line}")
        
        existing_data.append(data_to_save_val)
        existing_data = existing_data[-1200:] # Keep only the last 1200 entries

        with open(data_file, "w") as f:
            json.dump(existing_data, f, indent=None, separators=(',', ':')) # Compact JSON
        log_message("✅ Saved data to file.")
    except Exception as e:
        log_message(f"❌ Error saving data to file: {e}")


def get_logger_last_update_from_growatt(dynamic_plant_id):
    global last_logger_update_time_from_growatt
    # log_message(f"Fetching logger last update time for Plant ID: {dynamic_plant_id}")
    url = "https://server.growatt.com/panel/getDevicesByPlantList"
    payload = {
        'currPage': 1,
        'plantId': dynamic_plant_id
    }
    try:
        growatt_login2() # Ensure secondary login session is active
        response = session.post(url, headers=HEADERS, data=payload, timeout=10)
        response.raise_for_status()
        data_resp = response.json() # Renamed to avoid conflict
        
        if data_resp.get("result") == 1 and data_resp.get("obj") and data_resp["obj"].get("datas"):
            if data_resp["obj"]["datas"]: # Check if datas list is not empty
                logger_data = data_resp["obj"]["datas"][0] # Assuming first device
                if "lastUpdateTime" in logger_data:
                    fetched_time = logger_data["lastUpdateTime"]
                    # log_message(f"Received logger last update time: {fetched_time}")
                    last_logger_update_time_from_growatt = fetched_time
                    return fetched_time
                else:
                    log_message("⚠️ 'lastUpdateTime' not found in Growatt devices list response.")
            else:
                log_message("⚠️ 'datas' array is empty in Growatt devices list response.")
        else:
            log_message(f"⚠️ Unexpected Growatt devices list response structure or result: {data_resp}")
    
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Error fetching logger last update: {e}")
    except json.JSONDecodeError as e:
        log_message(f"❌ Error decoding JSON from Growatt devices list: {e}")
    except Exception as e:
        log_message(f"❌ An unexpected error occurred while fetching logger update time: {e}")
    
    last_logger_update_time_from_growatt = "N/A - Fetch Failed" # Update global on any failure
    return None


def monitor_growatt():
    global last_processed_time, current_data
    threshold_v = 80 # Renamed for clarity
    sent_lights_off = False
    sent_lights_on = False
    loop_counter = 0
    dyn_user_id, dyn_plant_id, dyn_inverter_sn, dyn_datalog_sn = None, None, None, None

    while True:
        try:
            if not all([dyn_user_id, dyn_plant_id, dyn_inverter_sn, dyn_datalog_sn]):
                log_message("Attempting to acquire Growatt IDs (re-login or initial).")
                dyn_user_id, dyn_plant_id, dyn_inverter_sn, dyn_datalog_sn = login_growatt()
                if not all([dyn_user_id, dyn_plant_id, dyn_inverter_sn, dyn_datalog_sn]):
                    log_message("Growatt ID fetching failed. Retrying in 60 seconds.")
                    time.sleep(60)
                    continue
                else:
                    log_message("Successfully acquired Growatt IDs for monitoring.")

            # Fetch detailed inverter data using the main API library
            inverter_api_data = api.storage_detail(dyn_inverter_sn)
            # log_message(f"Growatt API storage_detail data: {inverter_api_data}") # Can be verbose

            # Fetch the actual logger's last update time from the server
            get_logger_last_update_from_growatt(dyn_plant_id)

            ac_input_v_str = inverter_api_data.get("vGrid", "N/A")
            ac_input_f_str = inverter_api_data.get("freqGrid", "N/A")
            ac_output_v_str = inverter_api_data.get("outPutVolt", "N/A")
            ac_output_f_str = inverter_api_data.get("freqOutPut", "N/A")
            load_w_str = inverter_api_data.get("activePower", "N/A")
            battery_pct_str = inverter_api_data.get("capacity", "N/A")

            current_data.update({
                "ac_input_voltage": ac_input_v_str,
                "ac_input_frequency": ac_input_f_str,
                "ac_output_voltage": ac_output_v_str,
                "ac_output_frequency": ac_output_f_str,
                "load_power": load_w_str,
                "battery_capacity": battery_pct_str,
                "user_id": dyn_user_id,
                "plant_id": dyn_plant_id,
                "inverter_sn": dyn_inverter_sn,
                "datalog_sn": dyn_datalog_sn
            })
            last_processed_time = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
            # log_message(f"Updated current_data. Logger time: {last_logger_update_time_from_growatt}")

            loop_counter += 1
            if loop_counter >= 2: # Approx every 7 * 40s = 4.6 minutes
                timestamp_to_save = last_logger_update_time_from_growatt
                if "N/A" in timestamp_to_save or not timestamp_to_save : # Fallback if logger time failed
                     timestamp_to_save = last_processed_time

                data_to_save = {
                    "timestamp": timestamp_to_save,
                    "vGrid": ac_input_v_str,
                    "outPutVolt": ac_output_v_str,
                    "activePower": load_w_str,
                    "capacity": battery_pct_str,
                    "freqOutPut": ac_output_f_str # Assuming this is ac_output_f_str
                }
                save_data_to_file(data_to_save)
                loop_counter = 0

            # Telegram alert logic (only if enabled)
            if telegram_enabled and ac_input_v_str != "N/A":
                current_ac_input_v = 0.0
                try:
                    current_ac_input_v = float(ac_input_v_str)
                except ValueError:
                    log_message(f"Could not convert ac_input_v_str '{ac_input_v_str}' to float for alert.")
                    # Decide if you want to proceed or skip if conversion fails. Defaulting to 0.0.

                if current_ac_input_v < threshold_v and not sent_lights_off:
                    time.sleep(110) # Debounce
                    data_confirm = api.storage_detail(dyn_inverter_sn)
                    ac_input_v_confirm_str = data_confirm.get("vGrid", "N/A") # Default to N/A
                    
                    confirm_ac_val = 0.0
                    if ac_input_v_confirm_str != "N/A":
                        try:
                            confirm_ac_val = float(ac_input_v_confirm_str)
                        except ValueError:
                            log_message(f"Could not convert confirm ac_input_v '{ac_input_v_confirm_str}' to float.")
                    
                    if confirm_ac_val < threshold_v:
                        msg = f"""🔴🔴¡Se fue la luz en Acacías!🔴🔴
🕒 Hora del logger: {last_logger_update_time_from_growatt}
Nivel de batería    : {battery_pct_str} %
Voltaje de la red   : {ac_input_v_confirm_str} V / {ac_input_f_str} Hz
Voltaje del inversor: {ac_output_v_str} V / {ac_output_f_str} Hz
Consumo actual    : {load_w_str} W"""
                        send_telegram_message(msg)
                        sent_lights_off = True
                        sent_lights_on = False

                elif current_ac_input_v >= threshold_v and not sent_lights_on:
                    # This implies lights were off previously, or it's the first normal reading
                    if sent_lights_off: # Only send "lights on" if they were previously recorded as off
                        time.sleep(110) # Debounce
                        data_confirm = api.storage_detail(dyn_inverter_sn)
                        ac_input_v_confirm_str = data_confirm.get("vGrid", "N/A")

                        confirm_ac_val = threshold_v # Default to threshold to prevent message if "N/A"
                        if ac_input_v_confirm_str != "N/A":
                            try:
                                confirm_ac_val = float(ac_input_v_confirm_str)
                            except ValueError:
                                log_message(f"Could not convert confirm ac_input_v '{ac_input_v_confirm_str}' to float.")
                        
                        if confirm_ac_val >= threshold_v:
                            msg = f"""✅✅¡Llegó la luz en Acacías!✅✅
🕒 Hora del logger: {last_logger_update_time_from_growatt}
Nivel de batería    : {battery_pct_str} %
Voltaje de la red   : {ac_input_v_confirm_str} V / {ac_input_f_str} Hz
Voltaje del inversor: {ac_output_v_str} V / {ac_output_f_str} Hz
Consumo actual    : {load_w_str} W"""
                            send_telegram_message(msg)
                            sent_lights_on = True
                            sent_lights_off = False
                    else: # If lights were never recorded as off, ensure sent_lights_on is true
                        sent_lights_on = True 
                        sent_lights_off = False


        except Exception as e_monitor_loop:
            log_message(f"⚠️ Major error in monitor_growatt loop: {e_monitor_loop}")
            # Reset IDs to force re-login attempt in the next full loop iteration
            dyn_user_id, dyn_plant_id, dyn_inverter_sn, dyn_datalog_sn = None, None, None, None
            time.sleep(30) # Wait a bit before retrying the loop

        time.sleep(30) # Interval for the main monitoring loop

# --- Telegram Handlers ---
def start_command(update: Update, context: CallbackContext): # Renamed to avoid conflict
    chat_log.add(update.effective_chat.id)
    update.message.reply_text("¡Bienvenido al monitor Growatt! Usa /status para ver el estado del inversor.")

def send_status_command(update: Update, context: CallbackContext): # Renamed
    chat_log.add(update.effective_chat.id)
    # Get current time in UTC-5 for the message
    # local_now_time = (datetime.now() - timedelta(hours=5)).strftime("%H:%M:%S")
    # Using last_processed_time which is already localized
    msg = f"""⚡ /status Estado del Inversor /stop⚡
🕒 Hora Procesado App: {last_processed_time}
🕒 Hora Logger Growatt: {last_logger_update_time_from_growatt}
Voltaje Red         : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje Inversor    : {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo             : {current_data.get('load_power', 'N/A')} W
Batería             : {current_data.get('battery_capacity', 'N/A')}%
"""
    try:
        update.message.reply_text(msg)
        log_message(f"✅ Status sent to {update.effective_chat.id}")
    except Exception as e:
        log_message(f"❌ Failed to send status to {update.effective_chat.id}: {e}")

def send_chatlog_command(update: Update, context: CallbackContext): # Renamed
    chat_log.add(update.effective_chat.id)
    ids = "\n".join(str(cid) for cid in sorted(list(chat_log))) # Sort for consistent order
    update.message.reply_text(f"IDs registrados:\n{ids}")

def stop_bot_telegram_command(update: Update, context: CallbackContext):
    global telegram_enabled, updater
    update.message.reply_text("Comando /stop recibido. Intentando detener el bot de Telegram...")
    log_message("Bot stop requested via Telegram command.")
    if telegram_enabled and updater and updater.running:
        updater.stop() # This signals the polling thread to stop
        updater.is_idle = False # Allow polling loop to exit if stuck in idle
        telegram_enabled = False
        log_message("Telegram bot stopped via /stop command.")
        update.message.reply_text("Bot de Telegram detenido.")
    else:
        log_message("Telegram bot was not running or already stopped.")
        update.message.reply_text("Bot de Telegram no estaba activo.")

def initialize_telegram_bot():
    global updater, dp, TELEGRAM_TOKEN, telegram_enabled
    if not TELEGRAM_TOKEN or len(TELEGRAM_TOKEN) < 20: # Basic check for token format
        log_message("❌ Cannot start Telegram bot: TELEGRAM_TOKEN is missing or looks invalid.")
        telegram_enabled = False # Ensure it's marked as not enabled
        return False

    if updater and updater.running:
        log_message("Telegram bot is already running.")
        telegram_enabled = True # Ensure it's marked as enabled
        return True

    try:
        log_message("Initializing Telegram bot...")
        updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
        dp = updater.dispatcher
        dp.add_handler(CommandHandler("start", start_command))
        dp.add_handler(CommandHandler("status", send_status_command))
        dp.add_handler(CommandHandler("chatlog", send_chatlog_command))
        dp.add_handler(CommandHandler("stop", stop_bot_telegram_command))
        
        # Start polling in a non-blocking way (it creates its own threads)
        updater.start_polling()
        log_message("Telegram bot polling started successfully.")
        # telegram_enabled = True # Set this in the calling function upon success
        return True
    except Exception as e:
        log_message(f"❌ Error starting Telegram bot: {e}")
        if "token" in str(e).lower(): # More specific error for token issues
             log_message("❌ This might be due to an invalid Telegram token.")
        updater = None # Clear updater on failure
        dp = None
        telegram_enabled = False # Ensure it's marked as not enabled
        return False

# --- Start Background Monitoring Thread ---
monitor_thread = threading.Thread(target=monitor_growatt, daemon=True)
monitor_thread.start()
log_message("Growatt monitoring thread started.")

# --- Flask Routes ---
@app.route("/")
def home():
    global TELEGRAM_TOKEN # To access it for display
    displayed_token = "Not Set"
    if TELEGRAM_TOKEN and len(TELEGRAM_TOKEN) > 10:
        displayed_token = TELEGRAM_TOKEN[:5] + "..." + TELEGRAM_TOKEN[-5:]

    return render_template("home.html",
                           d=current_data,
                           last_growatt_update=last_logger_update_time_from_growatt,
                           plant_id=current_data.get("plant_id", "N/A"), # Dynamic plant_id
                           user_id=current_data.get("user_id", "N/A"),
                           inverter_sn=current_data.get("inverter_sn", "N/A"),
                           datalog_sn=current_data.get("datalog_sn", "N/A"),
                           telegram_status="Running" if telegram_enabled and updater and updater.running else "Stopped",
                           current_telegram_token=displayed_token
                           )

@app.route("/toggle_telegram", methods=["POST"])
def toggle_telegram():
    global telegram_enabled # We need to modify this global
    action = request.form.get('action')

    if action == 'start':
        if not (updater and updater.running): # Check if not already running
            log_message("Attempting to start Telegram bot via Flask UI.")
            if initialize_telegram_bot():
                telegram_enabled = True # Mark as enabled ONLY if initialization is successful
                log_message("Telegram bot enabled and started via Flask UI.")
            else:
                telegram_enabled = False # Ensure it's false if start failed
                log_message("Failed to start Telegram bot (check logs). It remains disabled.")
        else:
            telegram_enabled = True # Already running, ensure flag is correct
            log_message("Telegram bot is already running.")
            
    elif action == 'stop':
        if updater and updater.running:
            log_message("Attempting to stop Telegram bot via Flask UI.")
            updater.stop()
            # updater.is_idle = False # Might help if stop hangs, but usually not needed
            telegram_enabled = False # Mark as disabled
            log_message("Telegram bot stopped via Flask UI.")
        else:
            telegram_enabled = False # Already stopped, ensure flag is correct
            log_message("Telegram bot was not running to be stopped.")
    
    return redirect(url_for('home'))


@app.route("/update_telegram_token", methods=["POST"])
def update_telegram_token():
    global TELEGRAM_TOKEN, telegram_enabled, updater, dp
    new_token = request.form.get('new_telegram_token', "").strip()

    if not new_token or len(new_token) < 20: # Basic validation
        log_message("❌ No new valid Telegram token provided or token too short.")
        # Could add a flash message for Flask here if you have flash messaging setup
        return redirect(url_for('home'))

    log_message("Attempting to update Telegram token...")

    if updater and updater.running:
        log_message("Stopping existing Telegram bot for token update...")
        try:
            updater.stop()
            time.sleep(1) # Give it a moment to stop
            log_message("Existing Telegram bot stopped.")
        except Exception as e:
            log_message(f"⚠️ Error stopping existing Telegram bot: {e}")
        # In any case, clear old instances
        updater = None
        dp = None
        telegram_enabled = False # Ensure it's marked as disabled before restart

    TELEGRAM_TOKEN = new_token # Update to the new token
    log_message(f"Telegram token updated in config. Attempting to restart bot.")

    if initialize_telegram_bot(): # This will use the new TELEGRAM_TOKEN
        telegram_enabled = True
        log_message("✅ Telegram bot restarted successfully with the new token.")
    else:
        telegram_enabled = False # Failed to restart
        log_message("❌ Failed to restart Telegram bot with the new token. It remains disabled. Please check logs and token.")
        # TELEGRAM_TOKEN = "" # Optionally clear the bad token
        
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
            log_message(f"❌ Error decoding JSON from {data_file}: {e}. File might be corrupted. Resetting.")
            parsed_data = [] # Reset if file is corrupt
        except Exception as e: # Catch other potential file reading errors
            log_message(f"❌ General error reading data for charts from {data_file}: {e}. Resetting.")
            parsed_data = []
    else:
        log_message(f"⚠️ Data file not found or empty: {data_file}. Charts will be empty.")
        # Ensure file exists for next save, even if it was missing or empty
        if not os.path.exists(data_file) or os.path.getsize(data_file) == 0:
            try:
                with open(data_file, "w") as f_init:
                    f_init.write("[]")
                log_message(f"Initialized empty data file again: {data_file}")
            except Exception as e_init:
                log_message(f"❌ Error initializing empty data file: {e_init}")
    
    processed_data = []
    for entry in parsed_data:
        if 'timestamp' in entry and isinstance(entry['timestamp'], str):
            try:
                # Ensure timestamp has time part, add default if missing for strptime
                ts_str = entry['timestamp']
                if len(ts_str) == 10: # YYYY-MM-DD, append a default time
                    ts_str += " 00:00:00" 
                elif len(ts_str) < 19 : # Heuristic for incomplete timestamp
                    log_message(f"Potentially incomplete timestamp '{ts_str}', attempting to parse.")
                    # Potentially add default parts or skip

                entry['dt_timestamp'] = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
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
        reference_time = datetime.now() - timedelta(hours=5) # Localized 'now'

    cutoff_time = reference_time - timedelta(hours=max_duration_hours_to_send)
    filtered_data_for_frontend = [
        entry for entry in processed_data
        if entry['dt_timestamp'] >= cutoff_time
    ]

    # Use safe conversion functions
    timestamps = [entry['timestamp'] for entry in filtered_data_for_frontend] # Original string timestamp
    ac_input = [safe_float(entry.get('vGrid')) for entry in filtered_data_for_frontend]
    ac_output = [safe_float(entry.get('outPutVolt')) for entry in filtered_data_for_frontend]
    active_power = [safe_int(entry.get('activePower')) for entry in filtered_data_for_frontend]
    battery_capacity = [safe_int(entry.get('capacity')) for entry in filtered_data_for_frontend]

    return render_template("logs.html", # Assuming you have logs.html
                           timestamps=timestamps,
                           ac_input=ac_input,
                           ac_output=ac_output,
                           active_power=active_power,
                           battery_capacity=battery_capacity)

@app.route("/chatlog")
def chatlog_view():
    # Same as your version, using render_template_string
    # Ensure nav links are correct if you add/remove pages
    # (HTML content for chatlog page is identical to your last version)
    return render_template_string("""
        <html><head><title>Growatt Monitor - Chatlog</title><meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes"><style>body{font-family:Arial,sans-serif;margin:0;padding:0;}nav{background-color:#333;overflow:hidden;position:sticky;top:0;z-index:100;}nav ul{list-style-type:none;margin:0;padding:0;display:flex;justify-content:center;}nav ul li{padding:14px 20px;}nav ul li a{color:white;text-decoration:none;font-size:18px;}nav ul li a:hover{background-color:#ddd;color:black;}</style></head><body><nav><ul><li><a href="/">Home</a></li><li><a href="/logs">Logs</a></li><li><a href="/chatlog">Chatlog</a></li><li><a href="/console">Console</a></li><li><a href="/battery-chart">Battery Chart</a></li></ul></nav><h1>Chatlog</h1><pre>{{ chat_log_display }}</pre></body></html>
    """, chat_log_display="\n".join(str(cid) for cid in sorted(list(chat_log))))


@app.route("/console")
def console_view():
    # (HTML content for console page is identical to your last version)
    # Ensure nav links are correct
    return render_template_string("""
        <html><head><title>Console Logs</title><meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes"><style>body{font-family:Arial,sans-serif;margin:0;padding:0;}nav{background-color:#333;overflow:hidden;position:sticky;top:0;z-index:100;}nav ul{list-style-type:none;margin:0;padding:0;display:flex;justify-content:center;}nav ul li{padding:14px 20px;}nav ul li a{color:white;text-decoration:none;font-size:18px;}nav ul li a:hover{background-color:#ddd;color:black;}</style></head><body><nav><ul><li><a href="/">Home</a></li><li><a href="/logs">Logs</a></li><li><a href="/chatlog">Chatlog</a></li><li><a href="/console">Console</a></li><li><a href="/battery-chart">Battery Chart</a></li></ul></nav><h2>Console Output (últimos 5 minutos)</h2><pre style="white-space: pre-wrap; font-family: monospace; overflow-x: auto; word-wrap: break-word;">{{ logs }}</pre><h2>📦 Fetched Growatt Data (Initial Login)</h2><pre style="white-space: pre-wrap; font-family: monospace; overflow-x: auto; word-wrap: break-word;">{{ data }}</pre></body></html>
    """,
    logs="\n".join(m for _, m in console_logs), # Only messages, no need for inner newline
    data=pprint.pformat(fetched_data, indent=2, width=120))


@app.route("/battery-chart", methods=["GET", "POST"])
def battery_chart():
    global last_successful_growatt_update_time
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
        # Convert to float and replace 'N/A' with None for chart compatibility
        cleaned_data = [float(x) if (isinstance(x, (int, float)) or (isinstance(x, str) and x.replace('.', '', 1).isdigit())) else None for x in data_list]
        if not cleaned_data or all(x is None for x in cleaned_data): # Check if all data points are None
            return None
        return {"name": name, "data": cleaned_data, "color": color, "fillOpacity": 0.2, "lineWidth": 1}

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
        energy_series=energy_series,
        last_growatt_update=last_successful_growatt_update_time
    )

@app.route('/dn') # Download logs
def download_logs():
    try:
        return send_file(data_file, as_attachment=True, download_name="growatt_sensor_data.json", mimetype="application/json")
    except Exception as e:
        log_message(f"❌ Error downloading data file: {e}")
        return f"❌ Error downloading file: {e}", 500


if __name__ == '__main__':
    log_message("Starting Flask application...")
    # Consider adding a check here if TELEGRAM_TOKEN is set and call initialize_telegram_bot()
    # if you want the bot to attempt to start when the app starts, based on a config or env var.
    # For now, it's manually started via UI.
    app.run(host='0.0.0.0', port=8000) # debug=False for production
