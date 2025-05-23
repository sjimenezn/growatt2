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
import git # New import for GitPython

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
TELEGRAM_TOKEN = "7653969082:AAGJ_8TL2-MA0uCLgtx8UAyfEBRzCmFWyzG" # <--- YOUR CURRENT TOKEN
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
                existing_data_from_file = json.load(f) # Read as `existing_data_from_file` to avoid name collision
                if isinstance(existing_data_from_file, list) and existing_data_from_file:
                    last_entry = existing_data_from_file[-1]
                    # Filter out 'timestamp' and other non-sensor keys and store
                    last_saved_sensor_values.update({
                        'vGrid': last_entry.get('vGrid'),
                        'outPutVolt': last_entry.get('outPutVolt'),
                        'activePower': last_entry.get('activePower'),
                        'capacity': last_entry.get('capacity'),
                        'freqOutPut': last_entry.get('freqOutPut')
                    })
                    log_message(f"Initialized last_saved_sensor_values from file: {last_saved_sensor_values}")
        except json.JSONDecodeError as e:
            log_message(f"⚠️ Could not load last_saved_sensor_values from {data_file} due to JSON error: {e}")
        except Exception as e:
            log_message(f"⚠️ Could not load last_saved_sensor_values from {data_file}: {e}")

    while True:
        current_loop_datetime_utc_minus_5 = datetime.now() - timedelta(hours=5)
        current_loop_time_str = current_loop_datetime_utc_minus_5.strftime("%Y-%m-%d %H:%M:%S")

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
            raw_growatt_data = api.storage_detail(inverter_sn) # Use a different var name to differentiate from processed data
            log_message(f"Raw Growatt API data received: {raw_growatt_data}")

            # Extract new values for comparison and current_data update
            new_ac_input_v = raw_growatt_data.get("vGrid", "N/A")
            new_ac_input_f = raw_growatt_data.get("freqGrid", "N/A")
            new_ac_output_v = raw_growatt_data.get("outPutVolt", "N/A")
            new_ac_output_f = raw_growatt_data.get("freqOutPut", "N/A")
            new_load_w = raw_growatt_data.get("activePower", "N/A")
            new_battery_pct = raw_growatt_data.get("capacity", "N/A")

            # Create a dictionary of current sensor values for comparison with `last_saved_sensor_values`
            # Convert to appropriate types for consistent comparison if possible, or keep as strings.
            # Using str for consistency if "N/A" is possible.
            current_sensor_values_for_comparison = {
                "vGrid": str(new_ac_input_v),
                "outPutVolt": str(new_ac_output_v),
                "activePower": str(new_load_w),
                "capacity": str(new_battery_pct),
                "freqOutPut": str(new_ac_output_f)
            }
            # Note: freqGrid is not typically saved to file, so excluded from comparison if not needed for file saving.

            data_to_save_for_file = {}
            growatt_data_is_stale = False

            # Check if the fetched sensor values are IDENTICAL to the last saved ones
            # Ensure last_saved_sensor_values is not empty before comparison
            if last_saved_sensor_values and current_sensor_values_for_comparison == last_saved_sensor_values:
                growatt_data_is_stale = True
                log_message("⚠️ Detected Growatt data is identical to last saved values (stale). Saving NULLs for charts.")
                
                # If data is stale, prepare data_to_save with None for numerical values
                data_to_save_for_file = {
                    "timestamp": current_loop_time_str,
                    "vGrid": None, # Will become null in JSON
                    "outPutVolt": None,
                    "activePower": None,
                    "capacity": None,
                    "freqOutPut": None, 
                }
                # last_successful_growatt_update_time should NOT be updated here.
                # It should reflect when *fresh* data was last received.
            else:
                log_message("✅ New Growatt data received.")
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
                
                # `last_saved_sensor_values` will be updated by `save_data_to_file` if this data is saved.

            # Always update `current_data` with the most recently *received* values
            # (even if they are stale), for immediate display on the Flask home page.
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

            # Save data to file every 7 cycles (or approximately every 4.6 minutes)
            # regardless if it's new data or nulls due to staleness.
            # This ensures consistent timestamps in the historical data.
            if loop_counter >= 7:
                save_data_to_file(data_to_save_for_file)
                loop_counter = 0
            else:
                loop_counter += 1 # Increment counter for non-save cycles

        except Exception as e_inner:
            log_message(f"❌ Error during Growatt data fetch or processing (API error): {e_inner}")
            # If there's an API error, we do NOT update last_successful_growatt_update_time.
            # We also do NOT save a data point for this cycle to the file.
            # This will result in a real "gap" in the historical data, distinct from "stale data" (which logs nulls).
            
            # Reset IDs to force re-login attempt in next loop
            user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None 

        time.sleep(40) # Wait for 40 seconds before next API call

# --- GitHub Sync Config ---
GITHUB_REPO_URL = "https://github.com/sjimenezn/growatt2.git" # Your GitHub repository URL
GITHUB_USERNAME = "sjimenezn" # Your GitHub username
GITHUB_TOKEN = "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" # Your Personal Access Token (PAT)
GIT_PUSH_INTERVAL_MINS = 30 # Sync every 30 minutes
LOCAL_REPO_PATH = "." # Current directory where main.py and saved_data.json reside

def init_and_add_remote(repo_path, remote_url, username, token):
    """Initializes a git repo if not exists and sets up remote."""
    try:
        repo = git.Repo(repo_path)
        log_message("✅ Local directory is already a Git repository.")
    except git.InvalidGitRepositoryError:
        log_message("🔄 Initializing new Git repository...")
        repo = git.Repo.init(repo_path)
        log_message("✅ Git repository initialized.")

    # Ensure the remote exists and is correctly configured with PAT
    remote_name = "origin"
    configured_remote_url = f"https://{username}:{token}@{remote_url.split('//')[-1]}"

    if remote_name in repo.remotes:
        log_message(f"🔄 Updating existing remote '{remote_name}' URL with PAT.")
        with repo.remotes[remote_name].config_writer:
            repo.remotes[remote_name].url = configured_remote_url
    else:
        log_message(f"🔄 Adding new remote '{remote_name}' with URL: {configured_remote_url.replace(token, '************')}")
        repo.create_remote(remote_name, configured_remote_url)
    
    # Set up origin/main tracking if not already done
    try:
        if 'main' in repo.heads and not repo.heads.main.is_tracking():
            repo.heads.main.set_tracking_branch(repo.remotes.origin.refs.main)
            log_message("✅ Set local 'main' branch to track 'origin/main'.")
        elif 'main' not in repo.heads:
            log_message("🔄 Local 'main' branch not found, attempting to fetch and checkout 'origin/main'.")
            repo.git.fetch()
            if 'origin/main' in repo.remotes.origin.refs:
                repo.git.checkout('main', track=repo.remotes.origin.refs.main)
                log_message("✅ Checked out and tracking 'origin/main'.")
            else:
                log_message("⚠️ 'origin/main' does not exist. Cannot set tracking branch. Please push initial content to GitHub.")
        else: # Handle case where it's already tracking or 'main' is local but untracked
            log_message("✅ Local 'main' branch exists and is likely tracking 'origin/main'.")
            
    except Exception as e:
        log_message(f"⚠️ Error setting up tracking branch: {e}")

    return repo

def sync_github_repo():
    """Performs Git add, commit, and push operation."""
    log_message(f"Starting GitHub sync thread. Sync interval: {GIT_PUSH_INTERVAL_MINS} minutes.")
    
    # Check if essential GitHub credentials are provided
    if not GITHUB_REPO_URL or not GITHUB_USERNAME or not GITHUB_TOKEN:
        log_message("⚠️ GitHub credentials (URL, username, token) are not fully set. Skipping GitHub sync.")
        return

    # Perform initial setup outside the loop to avoid repeating it
    try:
        repo = init_and_add_remote(LOCAL_REPO_PATH, GITHUB_REPO_URL, GITHUB_USERNAME, GITHUB_TOKEN)
    except Exception as e:
        log_message(f"❌ FATAL: Initial Git setup failed: {e}. GitHub sync disabled.")
        return # Stop the thread if initial setup fails

    while True:
        time.sleep(GIT_PUSH_INTERVAL_MINS * 60) # Wait for the interval

        try:
            # Check for changes in saved_data.json
            if not os.path.exists(data_file):
                log_message(f"⚠️ Data file '{data_file}' not found, skipping Git sync.")
                continue

            # Check if there are uncommitted changes to saved_data.json
            changed_files = [item.a_path for item in repo.index.diff(None)]
            unstaged_files = repo.untracked_files 
            
            file_changed = data_file in changed_files or data_file in unstaged_files
            
            if not file_changed:
                log_message(f"⚙️ No changes detected in '{data_file}', skipping Git commit/push.")
                continue

            log_message(f"🔄 Committing and pushing '{data_file}' to GitHub...")
            repo.index.add([data_file])
            commit_message = f"Auto-update Growatt data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC-5)"
            
            try:
                repo.index.commit(commit_message)
                log_message(f"✅ Committed changes: '{commit_message}'")
            except git.exc.GitCommandError as e:
                if "nothing to commit, working tree clean" in str(e):
                    log_message("⚙️ Git: Nothing new to commit (might have been committed by previous run).")
                else:
                    log_message(f"❌ Git commit failed: {e}")
                    continue # Skip push if commit failed

            # Explicitly use the PAT for authentication during the push.
            push_remote_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@{GITHUB_REPO_URL.split('//')[-1]}"
            
            # Push to 'main' branch (adjust to 'master' if your repo uses it)
            repo.git.push(push_remote_url, 'main', '--force-with-lease')

            log_message("✅ Successfully pushed to GitHub.")

        except git.exc.GitCommandError as e:
            log_message(f"❌ Git command error during sync: {e}")
        except Exception as e:
            log_message(f"❌ An unexpected error occurred during GitHub sync: {e}")


# Telegram Handlers (unchanged)
def start(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    update.message.reply_text("¡Bienvenido al monitor Growatt! Usa /status para ver el estado del inversor.")

def send_status(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)

    timestamp = (datetime.now() - timedelta(hours=5)).strftime("%H:%M:%S")

    msg = f"""⚡ /status Estado del Inversor /stop⚡
        🕒 Hora--> {timestamp} 
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
        energy_series=energy_series
    )

@app.route('/dn')
def download_logs():
    try:
        return send_file(data_file, as_attachment=True, download_name="saved_data.json", mimetype="application/json")
    except Exception as e:
        log_message(f"❌ Error downloading file: {e}")
        return f"❌ Error downloading file: {e}", 500

# Start the GitHub sync thread after Flask app is defined and before it runs
github_sync_thread = threading.Thread(target=sync_github_repo, daemon=True)
github_sync_thread.start()
        
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
