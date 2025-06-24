import pytz
from flask import Flask, render_template, render_template_string, jsonify, request, send_file, redirect, url_for
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

# --- Pre-computation Logging ---
# This function is used by startup logic, so it needs to be defined early.
console_logs = []
def log_message(message):
    timestamped = f"{(datetime.now() - timedelta(hours=5)).strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now = time.time()
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 6000]

# --- File for saving data ---
data_file = "saved_data.json"

### NEW: Function to pull the single data file from the 'growatt' data repository on startup ###
def pull_data_file_from_repo():
    """
    Attempts to download the latest saved_data.json from the 'growatt' data repository.
    This is called on application startup to ensure the app has the latest data.
    """
    DATA_REPO_OWNER = "sjimenezn"
    DATA_REPO_NAME = "growatt"
    DATA_FILE_PATH = "saved_data.json"
    BRANCH = "main"  # Or "master", ensure this matches your repository's default branch

    token = os.getenv("GITHUB_PAT")
    if not token:
        log_message("⚠️ GITHUB_PAT not set. Cannot pull data file from remote. Will use local version if it exists.")
        return

    url = f"https://raw.githubusercontent.com/{DATA_REPO_OWNER}/{DATA_REPO_NAME}/{BRANCH}/{DATA_FILE_PATH}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.raw"
    }

    log_message(f"Attempting to pull '{DATA_FILE_PATH}' from the '{DATA_REPO_NAME}' data repository...")

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            with open(data_file, "wb") as f:  # Use 'wb' to write the binary content
                f.write(response.content)
            log_message(f"✅ Successfully pulled and saved '{DATA_FILE_PATH}' from '{DATA_REPO_NAME}'.")
        elif response.status_code == 404:
            log_message(f"⚠️ '{DATA_FILE_PATH}' not found in the data repository (404). A new file will be created locally if needed.")
        else:
            log_message(f"❌ Failed to pull '{DATA_FILE_PATH}'. Status Code: {response.status_code}. Response: {response.text[:200]}")
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Network error while trying to pull '{DATA_FILE_PATH}': {e}")


### NEW: Call the pull function on startup ###
pull_data_file_from_repo()


# Ensure the file exists and is initialized as an empty JSON array if the pull failed and file doesn't exist
if not os.path.exists(data_file) or os.path.getsize(data_file) == 0:
    with open(data_file, "w") as f:
        f.write("[]")  # Initialize with an empty JSON array
    print(f"Initialized empty data file: {data_file}")

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
    global last_processed_time, last_successful_growatt_update_time, last_saved_sensor_values, current_data
    threshold = 80
    grid_was_up = None  # Initialize state as unknown

    loop_counter = 0
    user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None

    # This block correctly attempts to load the last known state from the file
    if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
        try:
            with open(data_file, "r") as f:
                existing_data_from_file = json.load(f)
                if isinstance(existing_data_from_file, list) and existing_data_from_file:
                    last_entry = existing_data_from_file[-1]
                    last_saved_sensor_values.update({
                        'vGrid': last_entry.get('vGrid'),
                        'outPutVolt': last_entry.get('outPutVolt'),
                        'activePower': last_entry.get('activePower'),
                        'capacity': last_entry.get('capacity'),
                        'freqOutPut': last_entry.get('freqOutPut')
                    })
                    log_message(f"Initialized last_saved_sensor_values from file: {last_saved_sensor_values}")

                    if 'vGrid' in last_entry and last_entry['vGrid'] is not None:
                        try:
                            if float(last_entry['vGrid']) >= threshold:
                                grid_was_up = True
                                log_message("Initialized 'grid_was_up' to True based on last saved vGrid.")
                            else:
                                grid_was_up = False
                                log_message("Initialized 'grid_was_up' to False based on last saved vGrid.")
                        except (ValueError, TypeError):
                            log_message("Could not convert last saved vGrid to float for initial grid status.")
                            grid_was_up = None
        except json.JSONDecodeError as e:
            log_message(f"⚠️ Could not load last_saved_sensor_values from {data_file} due to JSON error: {e}")
        except Exception as e:
            log_message(f"⚠️ Could not load last_saved_sensor_values from {data_file}: {e}")

    while True:
        current_loop_datetime_utc_minus_5 = datetime.now() - timedelta(hours=5)
        current_loop_time_str = current_loop_datetime_utc_minus_5.strftime("%Y-%m-%d %H:%M:%S")
        growatt_data_is_stale = False

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

            current_sensor_values_for_comparison = {
                "vGrid": str(new_ac_input_v),
                "outPutVolt": str(new_ac_output_v),
                "activePower": str(new_load_w),
                "capacity": str(new_battery_pct),
                "freqOutPut": str(new_ac_output_f)
            }

            if last_saved_sensor_values and current_sensor_values_for_comparison == last_saved_sensor_values:
                growatt_data_is_stale = True
                log_message("⚠️ Detected Growatt data is identical to last saved values. Skipping file save for this cycle.")
            else:
                last_successful_growatt_update_time = current_loop_time_str
                data_to_save_for_file = {
                    "timestamp": last_successful_growatt_update_time,
                    "vGrid": new_ac_input_v,
                    "outPutVolt": new_ac_output_v,
                    "activePower": new_load_w,
                    "capacity": new_battery_pct,
                    "freqOutPut": new_ac_output_f,
                }
                if loop_counter >= 4:
                    save_data_to_file(data_to_save_for_file)
                    loop_counter = 0
                else:
                    loop_counter += 1

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

            if telegram_enabled:
                if current_data.get("ac_input_voltage") != "N/A":
                    try:
                        current_ac_input_v_float = float(current_data.get("ac_input_voltage"))
                    except (ValueError, TypeError):
                        current_ac_input_v_float = 0.0

                    alert_timestamp = last_successful_growatt_update_time

                    # --- START OF CORRECTED NOTIFICATION LOGIC ---

                    # CASE 1: Grid voltage is LOW (possible outage)
                    if current_ac_input_v_float < threshold:
                        # ONLY send a message if the grid was previously considered ONLINE.
                        if grid_was_up is True:
                            log_message(f"Voltage drop detected ({current_ac_input_v_float}V). Confirming in 110 seconds...")
                            time.sleep(110)
                            data_confirm = api.storage_detail(inverter_sn)
                            ac_input_v_confirm_str = data_confirm.get("vGrid", "0")
                            try:
                                current_ac_input_v_confirm = float(ac_input_v_confirm_str)
                            except (ValueError, TypeError):
                                current_ac_input_v_confirm = 0.0

                            if current_ac_input_v_confirm < threshold:
                                log_message(f"Confirmed outage ({current_ac_input_v_confirm}V). Sending Telegram alert.")
                                # Use the LATEST confirmed data for the message for accuracy
                                msg = f"""🔴🔴¡Se fue la luz en Acacías!🔴🔴
    🕒 Hora--> {alert_timestamp}
Nivel de batería     : {data_confirm.get('capacity', 'N/A')} %
Voltaje de la red    : {current_ac_input_v_confirm} V / {data_confirm.get('freqGrid', 'N/A')} Hz
Voltaje del inversor: {data_confirm.get('outPutVolt', 'N/A')} V / {data_confirm.get('freqOutPut', 'N/A')} Hz
Consumo actual     : {data_confirm.get('activePower', 'N/A')} W"""
                                send_telegram_message(msg)
                        
                        # Always update the state to reflect reality for the next cycle
                        grid_was_up = False

                    # CASE 2: Grid voltage is HIGH (normal)
                    elif current_ac_input_v_float >= threshold:
                        # ONLY send a message if the grid was previously considered OFFLINE.
                        if grid_was_up is False:
                            log_message(f"Voltage rise detected ({current_ac_input_v_float}V). Confirming in 110 seconds...")
                            time.sleep(110)
                            data_confirm = api.storage_detail(inverter_sn)
                            ac_input_v_confirm_str = data_confirm.get("vGrid", "0")
                            try:
                                current_ac_input_v_confirm = float(ac_input_v_confirm_str)
                            except (ValueError, TypeError):
                                current_ac_input_v_confirm = 0.0

                            if current_ac_input_v_confirm >= threshold:
                                log_message(f"Confirmed grid restoration ({current_ac_input_v_confirm}V). Sending Telegram alert.")
                                # Use the LATEST confirmed data for the message for accuracy
                                msg = f"""✅✅¡Llegó la luz en Acacías!✅✅
    🕒 Hora--> {alert_timestamp}
Nivel de batería     : {data_confirm.get('capacity', 'N/A')} %
Voltaje de la red    : {current_ac_input_v_confirm} V / {data_confirm.get('freqGrid', 'N/A')} Hz
Voltaje del inversor: {data_confirm.get('outPutVolt', 'N/A')} V / {data_confirm.get('freqOutPut', 'N/A')} Hz
Consumo actual     : {data_confirm.get('activePower', 'N/A')} W"""
                                send_telegram_message(msg)

                        # Always update the state to reflect reality for the next cycle
                        # This also sets the initial state on the very first run without sending an alert
                        grid_was_up = True
                    
                    # --- END OF CORRECTED NOTIFICATION LOGIC ---

        except Exception as e_inner:
            log_message(f"❌ Error during Growatt data fetch or processing (API error): {e_inner}")
            # Reset IDs to force a re-login on the next attempt
            user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None

        time.sleep(60)


# --- GitHub Sync Config ---
### MODIFIED: Changed the repo URL to point to the 'growatt' data repository ###
DATA_REPO_URL = "https://github.com/sjimenezn/growatt.git"
GITHUB_USERNAME = "sjimenezn"
GITHUB_TOKEN = os.getenv("GITHUB_PAT")
GIT_PUSH_INTERVAL_MINS = 15

def _perform_single_github_sync_operation(context_prefix="SYNC"):
    """
    Performs a Git sync operation, pushing saved_data.json to the DATA_REPO_URL.
    """
    base_working_dir = os.path.abspath(os.getcwd())

    TEMP_REPO_DIR_NAME = f"temp_git_repo_{context_prefix.lower()}"
    TEMP_REPO_PATH = os.path.join(base_working_dir, TEMP_REPO_DIR_NAME)

    EMPTY_TEMPLATE_DIR_NAME = f"empty_git_template_{context_prefix.lower()}"
    EMPTY_TEMPLATE_PATH = os.path.join(base_working_dir, EMPTY_TEMPLATE_DIR_NAME)

    FILE_TO_SYNC = "saved_data.json"
    original_git_template_dir_env = os.environ.get('GIT_TEMPLATE_DIR')

    if os.path.exists(TEMP_REPO_PATH):
        try:
            shutil.rmtree(TEMP_REPO_PATH)
            log_message(f"[{context_prefix}] Successfully removed existing TEMP_REPO_PATH.")
        except Exception as e_rm_initial:
            log_message(f"❌ [{context_prefix}] CRITICAL: Error removing TEMP_REPO_PATH {TEMP_REPO_PATH} at start: {e_rm_initial}. Sync aborted.")
            return False, f"Failed to remove pre-existing temp directory: {e_rm_initial}"

    try:
        os.makedirs(EMPTY_TEMPLATE_PATH, exist_ok=True)
        os.makedirs(os.path.join(EMPTY_TEMPLATE_PATH, "hooks"), exist_ok=True)
        os.environ['GIT_TEMPLATE_DIR'] = EMPTY_TEMPLATE_PATH
    except Exception as e_mkdir_template:
        log_message(f"⚠️ [{context_prefix}] Could not create or set empty template dir {EMPTY_TEMPLATE_PATH}: {e_mkdir_template}.")

    try:
        if not GITHUB_TOKEN:
            log_message(f"❌ [{context_prefix}] GITHUB_TOKEN (PAT) environment variable not set!")
            return False, "GitHub credentials not set (GITHUB_TOKEN)"
        if not GITHUB_USERNAME:
            log_message(f"❌ [{context_prefix}] GITHUB_USERNAME is not set!")
            return False, "GitHub credentials not set (GITHUB_USERNAME)"

        ### MODIFIED: Construct the clone URL using the new DATA_REPO_URL variable ###
        repo_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@{DATA_REPO_URL.split('//')[1]}"
        repo = Repo.clone_from(repo_url, TEMP_REPO_PATH)

        with repo.config_writer() as cw:
            cw.set_value("user", "name", f"GitHub Sync Bot ({context_prefix})")
            cw.set_value("user", "email", f"bot-{context_prefix.lower()}@example.com")

        source_file_path = os.path.join(base_working_dir, FILE_TO_SYNC)
        destination_file_path = os.path.join(TEMP_REPO_PATH, FILE_TO_SYNC)

        if os.path.exists(source_file_path):
            shutil.copy2(source_file_path, destination_file_path)
        else:
            log_message(f"❌ [{context_prefix}] Source file {source_file_path} not found. This will be committed as a deletion if the file was previously tracked.")

        repo.git.add(A=True)

        commit_message = f"Automated data sync ({context_prefix}): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        if repo.is_dirty(index=True, working_tree=False, untracked_files=False):
            repo.git.commit("-m", commit_message)
            log_message(f"✅ [{context_prefix}] Changes committed.")
        else:
            log_message(f"[{context_prefix}] No file content changes detected. Creating empty commit to mark sync: '{commit_message}'")
            repo.git.commit("--allow-empty", "-m", commit_message)
            log_message(f"✅ [{context_prefix}] Empty commit created.")

        origin = repo.remote(name='origin')
        origin.push()
        log_message(f"✅ [{context_prefix}] Changes pushed to GitHub.")

        return True, f"[{context_prefix}] Sync completed successfully"

    except git.GitCommandError as e_git:
        error_detail = f"Cmd({e_git.command}) failed due to: exit code({e_git.status})\n"
        error_detail += f"  cmdline: {' '.join(e_git.command)}\n"
        if hasattr(e_git, 'stderr') and e_git.stderr: error_detail += f"  stderr: '{e_git.stderr.strip()}'\n"
        if hasattr(e_git, 'stdout') and e_git.stdout: error_detail += f"  stdout: '{e_git.stdout.strip()}'"
        log_message(f"❌ [{context_prefix}] GitHub sync failed due to GitCommandError:\n{error_detail}")
        return False, f"GitCommandError: {error_detail}"
    except Exception as e_general:
        log_message(f"❌ [{context_prefix}] GitHub sync failed due to a general error: {type(e_general).__name__} - {e_general}")
        return False, str(e_general)
    finally:
        if 'GIT_TEMPLATE_DIR' in os.environ and os.environ.get('GIT_TEMPLATE_DIR') == EMPTY_TEMPLATE_PATH :
            if original_git_template_dir_env is None:
                del os.environ['GIT_TEMPLATE_DIR']
            else:
                os.environ['GIT_TEMPLATE_DIR'] = original_git_template_dir_env
                log_message(f"[{context_prefix}] Restored GIT_TEMPLATE_DIR to: {original_git_template_dir_env or 'None'}.")

        if os.path.exists(TEMP_REPO_PATH):
            try:
                shutil.rmtree(TEMP_REPO_PATH)
            except Exception as e_rm_final_repo:
                log_message(f"❌ [{context_prefix}] Error removing TEMP_REPO_PATH {TEMP_REPO_PATH} in finally block: {e_rm_final_repo}")

        if os.path.exists(EMPTY_TEMPLATE_PATH):
            try:
                shutil.rmtree(EMPTY_TEMPLATE_PATH)
            except Exception as e_rm_final_template:
                log_message(f"⚠️ [{context_prefix}] Error removing EMPTY_TEMPLATE_PATH {EMPTY_TEMPLATE_PATH} in finally block: {e_rm_final_template}")


def sync_github_repo():
    """Scheduled thread to sync data with GitHub."""
    log_message(f"🔁 [{datetime.now().strftime('%H:%M:%S')}] Starting GitHub sync thread (interval: {GIT_PUSH_INTERVAL_MINS} mins)")

    while True:
        time.sleep(GIT_PUSH_INTERVAL_MINS * 60)

        current_time_str = datetime.now().strftime('%H:%M:%S')
        log_message(f"[{current_time_str}] 🔁AUTO_SYNC: Triggering GitHub sync job.")

        success, message = _perform_single_github_sync_operation(context_prefix="AUTO_SYNC")

        log_message(f"[{datetime.now().strftime('%H:%M:%S')}] ✅AUTO_SYNC: Sync job result: Success={success}, Message='{message}'")


# Telegram Handlers (No changes in this section)
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

# Start GitHub Sync Thread
github_sync_thread = threading.Thread(target=sync_github_repo, daemon=True, name="GitHubSyncThread")
github_sync_thread.start()
log_message("GitHub sync thread starter initialized.")

# --- Flask Routes (No changes in this section) ---
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
    parsed_data = []
    if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
        try:
            with open(data_file, "r") as file: parsed_data = json.load(file)
            if not isinstance(parsed_data, list):
                log_message(f"❌ Data file {data_file} does not contain a JSON list. Resetting."); parsed_data = []
        except json.JSONDecodeError as e: log_message(f"❌ Error decoding JSON from {data_file}: {e}. File might be corrupted."); parsed_data = []
        except Exception as e: log_message(f"❌ General error reading data for charts from {data_file}: {e}"); parsed_data = []
    else:
        log_message(f"⚠️ Data file not found or empty: {data_file}. Charts will be empty.")
        if not os.path.exists(data_file) or os.path.getsize(data_file) == 0:
            try:
                with open(data_file, "w") as f: f.write("[]")
                log_message(f"Initialized empty data file: {data_file}")
            except Exception as e: log_message(f"❌ Error initializing empty data file: {e}")
    processed_data = []
    for entry in parsed_data:
        if 'timestamp' in entry and isinstance(entry['timestamp'], str):
            try: entry['dt_timestamp'] = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S"); processed_data.append(entry)
            except ValueError: log_message(f"Skipping entry with invalid timestamp format: {entry.get('timestamp')}")
        else: log_message(f"Skipping entry with missing or non-string timestamp: {entry}")
    processed_data.sort(key=lambda x: x['dt_timestamp'])
    max_duration_hours_to_send = 96
    reference_time = processed_data[-1]['dt_timestamp'] if processed_data else datetime.now()
    cutoff_time = reference_time - timedelta(hours=max_duration_hours_to_send)
    filtered_data_for_frontend = [e for e in processed_data if e['dt_timestamp'] >= cutoff_time]
    timestamps = [e['timestamp'] for e in filtered_data_for_frontend]
    ac_input = [float(e['vGrid']) if e.get('vGrid') is not None else None for e in filtered_data_for_frontend]
    ac_output = [float(e['outPutVolt']) if e.get('outPutVolt') is not None else None for e in filtered_data_for_frontend]
    active_power = [int(e['activePower']) if e.get('activePower') is not None else None for e in filtered_data_for_frontend]
    battery_capacity = [int(e['capacity']) if e.get('capacity') is not None else None for e in filtered_data_for_frontend]
    return render_template("logs.html", timestamps=timestamps, ac_input=ac_input, ac_output=ac_output,
                           active_power=active_power, battery_capacity=battery_capacity,
                           last_growatt_update=last_successful_growatt_update_time)

@app.route("/chatlog")
def chatlog_view():
    return render_template_string("""
        <html><head><title>Growatt Monitor - Chatlog</title><meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes">
        <style>body{font-family:Arial,sans-serif;margin:0;padding:0}nav{background-color:#333;overflow:hidden;position:sticky;top:0;z-index:100}nav ul{list-style-type:none;margin:0;padding:0;display:flex;justify-content:center}nav ul li{padding:14px 20px}nav ul li a{color:white;text-decoration:none;font-size:18px}nav ul li a:hover{background-color:#ddd;color:black}</style></head>
        <body><nav><ul><li><a href="/">Home</a></li><li><a href="/logs">Logs</a></li><li><a href="/chatlog">Chatlog</a></li><li><a href="/console">Console</a></li><li><a href="/details">Details</a></li><li><a href="/battery-chart">Battery Chart</a></li></ul></nav>
        <h1>Chatlog</h1><pre>{{ chat_log }}</pre></body></html>""", chat_log="\n".join(str(cid) for cid in sorted(list(chat_log))))

@app.route("/console")
def console_view():
    return render_template_string("""
        <html><head><title>Console Logs</title><meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes">
        <style>body{font-family:Arial,sans-serif;margin:0;padding:0}nav{background-color:#333;overflow:hidden;position:sticky;top:0;z-index:100}nav ul{list-style-type:none;margin:0;padding:0;display:flex;justify-content:center}nav ul li{padding:14px 20px}nav ul li a{color:white;text-decoration:none;font-size:18px}nav ul li a:hover{background-color:#ddd;color:black}</style></head>
        <body><nav><ul><li><a href="/">Home</a></li><li><a href="/logs">Logs</a></li><li><a href="/chatlog">Chatlog</a></li><li><a href="/console">Console</a></li><li><a href="/details">Details</a></li><li><a href="/battery-chart">Battery Chart</a></li></ul></nav>
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


@app.route('/dn')
def download_logs():
    try: return send_file(data_file, as_attachment=True, download_name="saved_data.json", mimetype="application/json")
    except Exception as e: log_message(f"❌ Error downloading file: {e}"); return f"❌ Error downloading file: {e}", 500

@app.route("/trigger_github_sync", methods=["POST"])
def trigger_github_sync():
    current_time_str = datetime.now().strftime('%H:%M:%S')
    log_message(f"[{current_time_str}] MANUAL_SYNC: Received manual GitHub sync request from web.")
    success, message = _perform_single_github_sync_operation(context_prefix="MANUAL_SYNC")
    log_message(f"[{datetime.now().strftime('%H:%M:%S')}] MANUAL_SYNC: Manual sync web request result: Success={success}, Message='{message}'")
    return redirect(url_for('logs'))

if __name__ == '__main__':
    log_message("Starting Flask development server.")
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)

