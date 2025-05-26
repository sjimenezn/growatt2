import pytz
from flask import Flask, render_template, render_template_string, jsonify, request, send_file, redirect, url_for, flash
import threading
import pprint
import json
import os
import time
import requests
import shutil
from datetime import datetime, timedelta
from growattServer import GrowattApi
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import git # New import for GitPython
from git import Repo

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

# NEW: Store the last successfully saved sensor values for comparison
last_saved_sensor_values = {}

console_logs = []

def log_message(message):
    timestamped = f"{(datetime.now() - timedelta(hours=5)).strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now = time.time()
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 6000]


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
    global last_saved_sensor_values # Make global so we can update it after saving
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
        
        # Add the new data point
        existing_data.append(data)

        # Keep only the last 1200 entries (or your desired limit)
        existing_data = existing_data[-1200:]

        # Write the entire list back as a single JSON array
        with open(data_file, "w") as f:
            json.dump(existing_data, f, indent=None, separators=(',', ':'))

        log_message("✅ Saved data to file as a JSON array.")
        
        # After successful save, update last_saved_sensor_values
        # Filter out 'timestamp' for comparison purposes for the next cycle
        comparable_data = {k: v for k, v in data.items() if k != 'timestamp'}
        last_saved_sensor_values.update(comparable_data)

    except Exception as e:
        log_message(f"❌ Error saving data to file: {e}")

def monitor_growatt():
    global last_processed_time, last_successful_growatt_update_time, last_saved_sensor_values
    threshold = 80
    sent_lights_off = False
    sent_lights_on = False

    loop_counter = 0

    user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None

    # On startup, attempt to populate last_saved_sensor_values from the last entry in the file
    if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
        try:
            with open(data_file, "r") as f:
                existing_data_from_file = json.load(f)
                if isinstance(existing_data_from_file, list) and existing_data_from_file:
                    last_entry = existing_data_from_file[-1]
                    # Make sure to handle potential None values from old 'null' entries in file
                    last_saved_sensor_values.update({
                        'vGrid': str(last_entry.get('vGrid')) if last_entry.get('vGrid') is not None else None,
                        'outPutVolt': str(last_entry.get('outPutVolt')) if last_entry.get('outPutVolt') is not None else None,
                        'activePower': str(last_entry.get('activePower')) if last_entry.get('activePower') is not None else None,
                        'capacity': str(last_entry.get('capacity')) if last_entry.get('capacity') is not None else None,
                        'freqOutPut': str(last_entry.get('freqOutPut')) if last_entry.get('freqOutPut') is not None else None
                    })
                    log_message(f"Initialized last_saved_sensor_values from file: {last_saved_sensor_values}")
        except json.JSONDecodeError as e:
            log_message(f"⚠️ Could not load last_saved_sensor_values from {data_file} due to JSON error: {e}")
        except Exception as e:
            log_message(f"⚠️ Could not load last_saved_sensor_values from {data_file}: {e}")
    else:
        log_message("No existing data file found or it's empty. last_saved_sensor_values remains empty.")


    while True:
        current_loop_datetime_utc_minus_5 = datetime.now() - timedelta(hours=5)
        current_loop_time_str = current_loop_datetime_utc_minus_5.strftime("%Y-%m-%d %H:%M:%S")

        should_save_to_file_this_cycle = False # New flag to control file saving
        data_to_save_for_file = {} # Initialize in case it's not set later

        try:
            # Always attempt to (re)login and get IDs if they are missing
            if user_id is None or plant_id is None or inverter_sn is None or datalog_sn is None:
                log_message("Attempting to acquire Growatt IDs (re-login or initial login).")
                user_id, plant_id, inverter_sn, datalog_sn = login_growatt()
                if user_id is None: # If login/ID fetching fails, wait and try again
                    log_message("Growatt login/ID fetching failed. Retrying in 60 seconds.")
                    time.sleep(60)
                    continue # Skip to next loop iteration

            # Attempt to fetch storage detail (main data point)
            raw_growatt_data = api.storage_detail(inverter_sn)
            log_message(f"Raw Growatt API data received: {raw_growatt_data}")

            # Extract new values for comparison and current_data update
            new_ac_input_v = raw_growatt_data.get("vGrid", "N/A")
            new_ac_input_f = raw_growatt_data.get("freqGrid", "N/A")
            new_ac_output_v = raw_growatt_data.get("outPutVolt", "N/A")
            new_ac_output_f = raw_growatt_data.get("freqOutPut", "N/A")
            new_load_w = raw_growatt_data.get("activePower", "N/A")
            new_battery_pct = raw_growatt_data.get("capacity", "N/A")

            # Create a dictionary of current sensor values for comparison with `last_saved_sensor_values`
            # Convert to string for consistent comparison with `last_saved_sensor_values` (which stores strings/None)
            current_sensor_values_for_comparison = {
                "vGrid": str(new_ac_input_v),
                "outPutVolt": str(new_ac_output_v),
                "activePower": str(new_load_w),
                "capacity": str(new_battery_pct),
                "freqOutPut": str(new_ac_output_f)
            }
            
            # Note: last_saved_sensor_values will now only contain strings of actual values, or None if the initial load found nulls.
            # If the inverter has been offline for a long time and `last_saved_sensor_values` holds `None`s,
            # and the Growatt API returns `N/A` or `0`, then `current_sensor_values_for_comparison != last_saved_sensor_values` will be true.
            # This is correct, as 'N/A' is different from None.

            # Check if the fetched sensor values are IDENTICAL to the last *saved actual* ones
            # If last_saved_sensor_values is empty (e.g., first run), always treat as new data.
            if last_saved_sensor_values and current_sensor_values_for_comparison == last_saved_sensor_values:
                log_message("⚠️ Detected Growatt data is identical to last saved values (stale from inverter). Skipping file save.")
                # DO NOT update last_successful_growatt_update_time.
                # DO NOT set should_save_to_file_this_cycle to True.
            else:
                log_message("✅ New Growatt data received from inverter.")
                last_successful_growatt_update_time = current_loop_time_str # Update only on fresh data

                # Prepare data to be saved to file with actual values
                data_to_save_for_file = {
                    "timestamp": last_successful_growatt_update_time, # Use the time when fresh data was received
                    "vGrid": new_ac_input_v,
                    "outPutVolt": new_ac_output_v,
                    "activePower": new_load_w,
                    "capacity": new_battery_pct,
                    "freqOutPut": new_ac_output_f,
                }
                should_save_to_file_this_cycle = True # Mark for saving

            # Always update `current_data` with the most recently *received* values
            # for immediate display on the Flask home page.
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

            last_processed_time = current_loop_time_str # This always updates as the loop processed.

            # --- Telegram Alerts ---
            # Telegram alerts should still use the *latest* available data from current_data,
            # even if stale, but their timestamp should reflect the last time *fresh* data arrived.
            if telegram_enabled:
                if current_data.get("ac_input_voltage") != "N/A":
                    try: # Convert to float for comparison if possible
                        current_ac_input_v_float = float(current_data.get("ac_input_voltage"))
                    except ValueError:
                            current_ac_input_v_float = 0.0 # Default if N/A

                    alert_timestamp = last_successful_growatt_update_time # Use the time of last *fresh* data
                    
                    if current_ac_input_v_float < threshold and not sent_lights_off:
                        # Re-fetch confirmation logic
                        time.sleep(110) # Wait a bit to confirm
                        data_confirm = api.storage_detail(inverter_sn) # Re-fetch to confirm
                        ac_input_v_confirm = data_confirm.get("vGrid", "0") # Default to "0"
                        try:
                            current_ac_input_v_confirm = float(ac_input_v_confirm)
                        except ValueError:
                            current_ac_input_v_confirm = 0.0

                        if current_ac_input_v_confirm < threshold: # Confirm again
                            msg = f"""🔴🔴¡Se fue la luz en Acacías!🔴🔴
        🕒 Hora--> {alert_timestamp}
Nivel de batería      : {current_data.get('battery_capacity', 'N/A')} %
Voltaje de la red     : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje del inversor: {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo actual     : {current_data.get('load_power', 'N/A')} W"""
                            send_telegram_message(msg)
                            sent_lights_off = True
                            sent_lights_on = False

                    elif current_ac_input_v_float >= threshold and not sent_lights_on:
                        # Re-fetch confirmation logic
                        time.sleep(110) # Wait a bit to confirm
                        data_confirm = api.storage_detail(inverter_sn) # Re-fetch to confirm
                        ac_input_v_confirm = data_confirm.get("vGrid", "0") # Default to "0"
                        try:
                            current_ac_input_v_confirm = float(ac_input_v_confirm)
                        except ValueError:
                            current_ac_input_v_confirm = 0.0

                        if current_ac_input_v_confirm >= threshold: # Confirm again
                            msg = f"""✅✅¡Llegó la luz en Acacías!✅✅
        🕒 Hora--> {alert_timestamp}
Nivel de batería      : {current_data.get('battery_capacity', 'N/A')} %
Voltaje de la red     : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje del inversor: {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo actual     : {current_data.get('load_power', 'N/A')} W"""
                            send_telegram_message(msg)
                            sent_lights_on = True
                            sent_lights_off = False

            # Save data to file ONLY IF should_save_to_file_this_cycle is True
            # AND it's time for the loop_counter to trigger a save.
            if should_save_to_file_this_cycle and loop_counter >= 7:
                save_data_to_file(data_to_save_for_file)
                loop_counter = 0 # Reset counter only if save actually happened
            elif should_save_to_file_this_cycle: # Increment even if not saving due to counter
                loop_counter += 1
            # If should_save_to_file_this_cycle is False, do nothing for the counter.

        except Exception as e_inner:
            log_message(f"❌ Error during Growatt data fetch or processing (API error): {e_inner}")
            # If there's an API error, we do NOT update last_successful_growatt_update_time.
            # We also do NOT save a data point for this cycle to the file.
            
            # Reset IDs to force re-login attempt in next loop
            user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None 

        time.sleep(40) # Wait for 40 seconds before next API call

# --- GitHub Sync Config ---
GITHUB_REPO_URL = "https://github.com/sjimenezn/growatt2.git"
GITHUB_USERNAME = "sjimenezn"
GITHUB_TOKEN = os.getenv("GITHUB_PAT")  # Get from environment variable
GIT_PUSH_INTERVAL_MINS = 5 # Changed to 5 minutes to align with data saving
LOCAL_REPO_PATH = "."

def _perform_single_github_sync_operation():
    """Performs a Git sync operation focusing only on saved_data.json, forcing a commit."""
    try:
        if not GITHUB_TOKEN:
            log_message("❌ GITHUB_PAT environment variable not set!")
            return False, "GitHub credentials not set"

        TEMP_DIR = "temp_repo"
        FILE_TO_SYNC = "saved_data.json"

        # Clean up previous temp directory if it exists
        if os.path.exists(TEMP_DIR):
            log_message(f"Cleaning up existing temp repo: {TEMP_DIR}")
            shutil.rmtree(TEMP_DIR, ignore_errors=True)

        # Clone the repo
        log_message(f"Cloning repo into {TEMP_DIR}...")
        repo = Repo.clone_from(
            f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/sjimenezn/growatt2.git",
            TEMP_DIR,
            depth=1  # Only get latest commit
        )
        log_message("Repo cloned successfully.")

        # Configure git user identity
        with repo.config_writer() as git_config:
            git_config.set_value("user", "name", "Growatt Data Sync Bot")
            git_config.set_value("user", "email", "growatt-sync@example.com")
        log_message("Git user identity configured.")

        # Copy our current data file to the repo
        if os.path.exists(FILE_TO_SYNC):
            shutil.copy2(FILE_TO_SYNC, os.path.join(TEMP_DIR, FILE_TO_SYNC))
            log_message(f"Copied local {FILE_TO_SYNC} to temp repo.")
        else:
            log_message(f"❌ Local {FILE_TO_SYNC} not found. Cannot sync.")
            return False, "Data file not found"

        # Git operations:
        # 1. Add the file, explicitly forcing if it's already staged or unchanged
        log_message(f"Staging {FILE_TO_SYNC} for commit...")
        repo.git.add("--force", FILE_TO_SYNC) # Use --force to ensure it's staged
        log_message(f"{FILE_TO_SYNC} staged.")

        # 2. Check if there are actual changes before committing
        # This is a more robust way to handle the "nothing to commit" situation
        # and prevent unnecessary empty commits unless explicitly desired.
        index_diff = repo.index.diff("HEAD")
        if not index_diff and not repo.untracked_files:
            log_message("No actual changes detected in saved_data.json. Committing with --allow-empty.")
            # If no actual content change, commit an empty commit to mark the timestamp
            repo.git.commit("--allow-empty", "-m", f"Keepalive / No data change - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            log_message("Changes detected in saved_data.json. Committing normally.")
            repo.git.commit("-m", f"Update {FILE_TO_SYNC} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        log_message("Pushing to remote...")
        repo.git.push()
        
        log_message("✅ Successfully synced saved_data.json to GitHub")
        return True, "Sync completed"
    
    except Exception as e:
        log_message(f"❌ GitHub sync failed: {e}")
        # Ensure temp directory is cleaned up even on failure
        if 'TEMP_DIR' in locals() and os.path.exists(TEMP_DIR):
            log_message(f"Cleaning up temp repo after failure: {TEMP_DIR}")
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
        return False, str(e)

def sync_github_repo():
    """Scheduled thread to sync data with GitHub"""
    log_message(f"🔁 Starting GitHub sync thread (interval: {GIT_PUSH_INTERVAL_MINS} mins)")
    
    while True:
        time.sleep(GIT_PUSH_INTERVAL_MINS * 60) # Convert minutes to seconds
        success, message = _perform_single_github_sync_operation()
        log_message(f"Sync result: {message}")

# Start the GitHub sync thread
github_sync_thread = threading.Thread(target=sync_github_repo, daemon=True)
github_sync_thread.start()



# --- Flask Routes ---
@app.route("/")
def home():
    global TELEGRAM_TOKEN, last_successful_growatt_update_time
    displayed_token = TELEGRAM_TOKEN
    if TELEGRAM_TOKEN and len(TELEGRAM_TOKEN) > 10:
        displayed_token = TELEGRAM_TOKEN[:5] + "..." + TELEGRAM_TOKEN[-5:]

    return render_template("home.html",
        d=current_data,
        last_growatt_update=last_successful_growatt_update_time, # This now correctly shows last *fresh* data
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
def logs():
    global last_successful_growatt_update_time
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
    # Handle None values for chart data by explicitly converting to float for numbers,
    # but allowing None to pass through.
    ac_input = [float(entry['vGrid']) if entry.get('vGrid') is not None else None for entry in filtered_data_for_frontend]
    ac_output = [float(entry['outPutVolt']) if entry.get('outPutVolt') is not None else None for entry in filtered_data_for_frontend]
    active_power = [int(entry['activePower']) if entry.get('activePower') is not None else None for entry in filtered_data_for_frontend]
    battery_capacity = [int(entry['capacity']) if entry.get('capacity') is not None else None for entry in filtered_data_for_frontend]

    return render_template("logs.html",
        timestamps=timestamps,
        ac_input=ac_input,
        ac_output=ac_output,
        active_power=active_power,
        battery_capacity=battery_capacity,
        last_growatt_update=last_successful_growatt_update_time)

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

@app.route('/dn')
def download_logs():
    try:
        return send_file(data_file, as_attachment=True, download_name="saved_data.json", mimetype="application/json")
    except Exception as e:
        log_message(f"❌ Error downloading file: {e}")
        return f"❌ Error downloading file: {e}", 500

@app.route("/trigger_github_sync", methods=["POST"])
def trigger_github_sync():
    """Manual trigger endpoint for GitHub sync"""
    log_message("Received manual GitHub sync request")
    success, message = _perform_single_github_sync_operation()
    # if success:
    #     flash("GitHub sync initiated successfully!", "success")
    # else:
    #     flash(f"GitHub sync failed: {message}", "error")
    return redirect(url_for('logs'))


