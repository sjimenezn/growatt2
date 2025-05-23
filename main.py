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
import shutil # New import for file copying

# --- File for saving data ---
data_file_name = "saved_data.json"
data_file_test_name = "saved_data_test.json" # New file for GitHub upload

# Ensure the file exists and is initialized as an empty JSON array
# This will be overridden by git clone/pull for persistence
if not os.path.exists(data_file_name) or os.path.getsize(data_file_name) == 0:
    with open(data_file_name, "w") as f:
        f.write("[]")  # Initialize with an empty JSON array
    print(f"Initialized empty data file: {data_file_name}")

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
        if os.path.exists(data_file_name) and os.path.getsize(data_file_name) > 0:
            with open(data_file_name, "r") as f:
                try:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        log_message(f"⚠️ Warning: {data_file_name} did not contain a JSON list. Attempting to convert.")
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
                                log_message(f"❌ Error decoding existing JSON line in {data_file_name}: {stripped_line} - {e}")

        existing_data.append(data)
        existing_data = existing_data[-1200:] # Keep only the last 1200 entries

        with open(data_file_name, "w") as f:
            json.dump(existing_data, f, indent=None, separators=(',', ':'))

        log_message(f"✅ Saved data to file {data_file_name} as a JSON array.")

        comparable_data = {k: v for k, v in data.items() if k != 'timestamp'}
        last_saved_sensor_values.update(comparable_data)

    except Exception as e:
        log_message(f"❌ Error saving data to {data_file_name}: {e}")

def monitor_growatt():
    global last_processed_time, last_successful_growatt_update_time, last_saved_sensor_values
    threshold = 80
    sent_lights_off = False
    sent_lights_on = False
    user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None

    if os.path.exists(data_file_name) and os.path.getsize(data_file_name) > 0:
        try:
            with open(data_file_name, "r") as f:
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
                    log_message(f"Initialized last_saved_sensor_values from {data_file_name}: {last_saved_sensor_values}")
        except Exception as e:
            log_message(f"⚠️ Could not load last_saved_sensor_values from {data_file_name}: {e}")

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
            log_message(f"Raw Growatt API data received: {raw_growatt_data}")

            new_ac_input_v = raw_growatt_data.get("vGrid", "N/A")
            new_ac_input_f = raw_growatt_data.get("freqGrid", "N/A")
            new_ac_output_v = raw_growatt_data.get("outPutVolt", "N/A")
            new_ac_output_f = raw_growatt_data.get("freqOutPut", "N/A")
            new_load_w = raw_growatt_data.get("activePower", "N/A")
            new_battery_pct = raw_growatt_data.get("capacity", "N/A")

            last_successful_growatt_update_time = current_loop_time_str

            data_to_save_for_file = {
                "timestamp": last_successful_growatt_update_time,
                "vGrid": new_ac_input_v,
                "outPutVolt": new_ac_output_v,
                "activePower": new_load_w,
                "capacity": new_battery_pct,
                "freqOutPut": new_ac_output_f,
            }

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
                current_ac_input_v_float = 0.0
                if current_data.get("ac_input_voltage") != "N/A":
                    try:
                        current_ac_input_v_float = float(current_data.get("ac_input_voltage"))
                    except ValueError:
                        pass # current_ac_input_v_float remains 0.0

                alert_timestamp = last_successful_growatt_update_time

                if current_ac_input_v_float < threshold and not sent_lights_off:
                    time.sleep(110)
                    data_confirm = api.storage_detail(inverter_sn)
                    ac_input_v_confirm_str = data_confirm.get("vGrid", "0")
                    current_ac_input_v_confirm = 0.0
                    try:
                        current_ac_input_v_confirm = float(ac_input_v_confirm_str)
                    except ValueError:
                        pass
                    if current_ac_input_v_confirm < threshold:
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
                    time.sleep(110)
                    data_confirm = api.storage_detail(inverter_sn)
                    ac_input_v_confirm_str = data_confirm.get("vGrid", "0")
                    current_ac_input_v_confirm = 0.0
                    try:
                        current_ac_input_v_confirm = float(ac_input_v_confirm_str)
                    except ValueError:
                        pass
                    if current_ac_input_v_confirm >= threshold:
                        msg = f"""✅✅¡Llegó la luz en Acacías!✅✅
    🕒 Hora--> {alert_timestamp}
Nivel de batería      : {current_data.get('battery_capacity', 'N/A')} %
Voltaje de la red     : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje del inversor: {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo actual     : {current_data.get('load_power', 'N/A')} W"""
                        send_telegram_message(msg)
                        sent_lights_on = True
                        sent_lights_off = False
            save_data_to_file(data_to_save_for_file)
        except Exception as e_inner:
            log_message(f"❌ Error during Growatt data fetch or processing (API error): {e_inner}")
            user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None
        time.sleep(40)

# --- GitHub Sync Config ---
GITHUB_REPO_URL = os.getenv("GITHUB_REPO_URL", "github.com/sjimenezn/growatt2.git")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "sjimenezn")
GITHUB_TOKEN = os.getenv("GITHUB_PAT")
GIT_PUSH_INTERVAL_MINS = int(os.getenv("GIT_PUSH_INTERVAL_MINS", "30"))
LOCAL_REPO_PATH = os.getenv("LOCAL_REPO_PATH", ".")

g_repo = None
data_file = os.path.join(LOCAL_REPO_PATH, data_file_name) # Path to the original data file
data_file_test = os.path.join(LOCAL_REPO_PATH, data_file_test_name) # Path to the test data file for GitHub


def init_and_add_remote(repo_path, remote_url, username, token):
    repo = None
    try:
        try:
            repo = git.Repo(repo_path)
            log_message("✅ Local directory is already a Git repository.")
        except git.InvalidGitRepositoryError:
            log_message("🔄 Initializing new Git repository...")
            repo = git.Repo.init(repo_path)
            log_message("✅ Git repository initialized.")
        if repo is None:
            raise Exception("Failed to initialize or get Git repository object.")
        remote_name = "origin"
        configured_remote_url = f"https://{username}:{token}@{remote_url}"
        if remote_name in repo.remotes:
            with repo.remotes[remote_name].config_writer as cw:
                cw.set("url", configured_remote_url)
        else:
            repo.create_remote(remote_name, configured_remote_url)
        repo.git.fetch()
        if 'main' not in repo.heads:
            repo.git.checkout('-b', 'main', 'origin/main')
        else:
            if repo.active_branch.name != 'main':
                repo.git.checkout('main')
            try:
                stdout_str, _ = repo.git.rev_parse('--abbrev-ref', '--symbolic-full-name', 'main@{u}', with_extended_output=True)
                if stdout_str.strip() != 'origin/main':
                    repo.heads.main.set_tracking_branch(repo.remotes.origin.refs.main)
            except git.exc.GitCommandError:
                try:
                    repo.heads.main.set_tracking_branch(repo.remotes.origin.refs.main)
                except Exception as set_e:
                    log_message(f"❌ Failed to set tracking branch for 'main': {set_e}")
    except Exception as e:
        log_message(f"⚠️ Error in init_and_add_remote: {e}")
        return None
    return repo


def _perform_single_github_sync_operation(repo_obj_param=None):
    log_message("🔄 Attempting GitHub sync operation with test file...")
    repo = repo_obj_param if repo_obj_param is not None else g_repo

    if repo is None:
        log_message("❌ Git repository object is not initialized. Cannot perform sync.")
        return False, "Git repository not initialized."
    if not GITHUB_REPO_URL or not GITHUB_USERNAME or not GITHUB_TOKEN:
        log_message("⚠️ GitHub credentials are not fully set. Skipping Git operation.")
        return False, "GitHub credentials not fully set."

    try:
        # --- Copy saved_data.json to saved_data_test.json ---
        if not os.path.exists(data_file):
            log_message(f"⚠️ Original data file '{data_file}' not found. Cannot copy to test file.")
            return False, f"Original data file {data_file_name} not found."
        try:
            shutil.copy2(data_file, data_file_test)
            log_message(f"✅ Copied '{data_file_name}' to '{data_file_test_name}'.")
        except Exception as e_copy:
            log_message(f"❌ Error copying '{data_file_name}' to '{data_file_test_name}': {e_copy}")
            return False, f"Error copying to {data_file_test_name}."

        current_branch = repo.active_branch.name
        if current_branch != 'main':
            log_message(f"Switching from '{current_branch}' to 'main' branch.")
            repo.git.checkout('main')
            log_message("✅ Switched to 'main' branch.")

        # --- Stage and commit BEFORE pull if data_file_test has changes (optional, but good if other manual changes occur) ---
        if os.path.exists(data_file_test): # Check the test file now
            if repo.is_dirty(path=data_file_test, untracked_files=True):
                log_message(f"🔄 Detected uncommitted changes for '{data_file_test_name}'. Staging before pull.")
                repo.index.add([data_file_test])
                if repo.index.diff("HEAD"):
                    commit_message = f"Pre-pull commit of Growatt test data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC-5)"
                    repo.index.commit(commit_message)
                    log_message(f"✅ Pre-pull committed changes for '{data_file_test_name}': '{commit_message}'")
                else:
                    log_message(f"⚙️ No new changes to commit for '{data_file_test_name}' before pull, but file was dirty.")
            else:
                log_message(f"⚙️ No uncommitted changes for '{data_file_test_name}' detected before pull.")
        else:
            log_message(f"⚠️ Test data file '{data_file_test_name}' not found before pull, skipping pre-pull commit check.")

        log_message("🔄 Pulling latest changes from GitHub...")
        pull_result = repo.git.pull('--rebase', 'origin', 'main')
        log_message(f"✅ Git pull result: {pull_result}")

        if not os.path.exists(data_file_test):
            log_message(f"⚠️ Test data file '{data_file_test_name}' not found after pull. Sync aborted.")
            return False, f"Test data file {data_file_test_name} not found after pull."

        # Add the test file to be committed
        log_message(f"🔄 Staging '{data_file_test_name}' for commit...")
        repo.index.add([data_file_test])

        if not repo.index.diff("HEAD"): # Check if there are staged changes
            log_message(f"⚙️ No changes detected in '{data_file_test_name}' after pull/add, skipping commit/push.")
            return True, f"No changes in {data_file_test_name} to push."

        commit_message = f"Auto-update Growatt test data ({data_file_test_name}): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC-5)"
        repo.index.commit(commit_message)
        log_message(f"✅ Committed changes for '{data_file_test_name}': '{commit_message}'")

        push_remote_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@{GITHUB_REPO_URL}"
        repo.git.push(push_remote_url, 'main', '--force-with-lease')
        log_message(f"✅ Successfully pushed '{data_file_test_name}' to GitHub.")
        return True, f"Successfully pushed {data_file_test_name}."

    except git.exc.GitCommandError as e:
        error_message = e.stderr.strip() if isinstance(e.stderr, str) else \
                        e.stderr.decode('utf-8').strip() if isinstance(e.stderr, bytes) else str(e)
        log_message(f"❌ Git command error during sync: {error_message}")
        return False, f"Git command error: {error_message}"
    except Exception as e:
        log_message(f"❌ An unexpected error occurred during GitHub sync: {e}")
        return False, f"Unexpected error: {e}"


def sync_github_repo():
    log_message(f"Starting scheduled GitHub sync thread. Sync interval: {GIT_PUSH_INTERVAL_MINS} minutes.")
    if not GITHUB_REPO_URL or not GITHUB_USERNAME or not GITHUB_TOKEN:
        log_message("⚠️ GitHub credentials not fully set for scheduled sync. Thread will not run.")
        return
    global g_repo
    repo = None
    try:
        if not os.path.exists(os.path.join(LOCAL_REPO_PATH, '.git')):
            authenticated_clone_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@{GITHUB_REPO_URL}"
            git.Repo.clone_from(authenticated_clone_url, LOCAL_REPO_PATH, branch='main')
            repo = git.Repo(LOCAL_REPO_PATH)
        else:
            repo = init_and_add_remote(LOCAL_REPO_PATH, GITHUB_REPO_URL, GITHUB_USERNAME, GITHUB_TOKEN)
        if repo is None:
            raise Exception("Git repository object is None after initial setup.")
        if repo.active_branch.name != 'main':
             repo.git.checkout('main')
        repo.git.pull('--rebase', 'origin', 'main')
    except Exception as e:
        log_message(f"❌ FATAL: Initial Git clone/pull setup for scheduled sync failed: {e}. Thread disabled.")
        return
    g_repo = repo
    while True:
        time.sleep(GIT_PUSH_INTERVAL_MINS * 60)
        log_message(f"Scheduled GitHub sync triggered for {data_file_test_name}.")
        _perform_single_github_sync_operation(g_repo)

# Telegram Handlers
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
        log_message("Telegram bot is already running.")
        return True
    try:
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
        log_message(f"❌ Error starting Telegram bot: {e}")
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
        if initialize_telegram_bot():
            telegram_enabled = True
    elif action == 'stop' and telegram_enabled:
        if updater and updater.running:
            updater.stop()
            telegram_enabled = False
    return redirect(url_for('home'))

@app.route("/update_telegram_token", methods=["POST"])
def update_telegram_token():
    global TELEGRAM_TOKEN, telegram_enabled, updater, dp
    new_token = request.form.get('new_telegram_token')
    if not new_token:
        return redirect(url_for('home'))
    if updater and updater.running:
        updater.stop()
        time.sleep(1)
        updater = None
        dp = None
    TELEGRAM_TOKEN = new_token
    if initialize_telegram_bot():
        telegram_enabled = True
    else:
        telegram_enabled = False
    return redirect(url_for('home'))

@app.route("/logs")
def charts_view():
    global last_successful_growatt_update_time
    parsed_data = []
    if os.path.exists(data_file) and os.path.getsize(data_file) > 0: # Read from original data_file for charts
        try:
            with open(data_file, "r") as file:
                parsed_data = json.load(file)
            if not isinstance(parsed_data, list):
                parsed_data = []
        except Exception as e:
            log_message(f"❌ Error reading/decoding JSON from {data_file}: {e}")
            parsed_data = []
    else:
        if not os.path.exists(data_file) or os.path.getsize(data_file) == 0:
            try:
                with open(data_file, "w") as f: f.write("[]")
            except Exception as e:
                log_message(f"❌ Error initializing empty data file {data_file}: {e}")
    processed_data = []
    for entry in parsed_data:
        if 'timestamp' in entry and isinstance(entry['timestamp'], str):
            try:
                entry['dt_timestamp'] = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
                processed_data.append(entry)
            except ValueError:
                pass
    processed_data.sort(key=lambda x: x['dt_timestamp'])
    max_duration_hours_to_send = 96
    reference_time = processed_data[-1]['dt_timestamp'] if processed_data else datetime.now()
    cutoff_time = reference_time - timedelta(hours=max_duration_hours_to_send)
    filtered_data_for_frontend = [entry for entry in processed_data if entry['dt_timestamp'] >= cutoff_time]
    timestamps = [entry['timestamp'] for entry in filtered_data_for_frontend]
    ac_input = [float(entry['vGrid']) if entry.get('vGrid') is not None else None for entry in filtered_data_for_frontend]
    ac_output = [float(entry['outPutVolt']) if entry.get('outPutVolt') is not None else None for entry in filtered_data_for_frontend]
    active_power = [int(entry['activePower']) if entry.get('activePower') is not None else None for entry in filtered_data_for_frontend]
    battery_capacity = [int(entry['capacity']) if entry.get('capacity') is not None else None for entry in filtered_data_for_frontend]
    return render_template("logs.html",
        timestamps=timestamps, ac_input=ac_input, ac_output=ac_output,
        active_power=active_power, battery_capacity=battery_capacity,
        last_growatt_update=last_successful_growatt_update_time)

@app.route("/chatlog")
def chatlog_view():
    return render_template_string("""
        <html><head><title>Growatt Monitor - Chatlog</title><meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes"><style>body{font-family:Arial,sans-serif;margin:0;padding:0}nav{background-color:#333;overflow:hidden;position:sticky;top:0;z-index:100}nav ul{list-style-type:none;margin:0;padding:0;display:flex;justify-content:center}nav ul li{padding:14px 20px}nav ul li a{color:white;text-decoration:none;font-size:18px}nav ul li a:hover{background-color:#ddd;color:black}</style></head><body><nav><ul><li><a href="/">Home</a></li><li><a href="/logs">Logs</a></li><li><a href="/chatlog">Chatlog</a></li><li><a href="/console">Console</a></li><li><a href="/details">Details</a></li><li><a href="/battery-chart">Battery Chart</a></li></ul></nav><h1>Chatlog</h1><pre>{{ chat_log }}</pre></body></html>
    """, chat_log="\n".join(str(cid) for cid in sorted(list(chat_log))))

@app.route("/console")
def console_view():
    return render_template_string("""
        <html><head><title>Console Logs</title><meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes"><style>body{font-family:Arial,sans-serif;margin:0;padding:0}nav{background-color:#333;overflow:hidden;position:sticky;top:0;z-index:100}nav ul{list-style-type:none;margin:0;padding:0;display:flex;justify-content:center}nav ul li{padding:14px 20px}nav ul li a{color:white;text-decoration:none;font-size:18px}nav ul li a:hover{background-color:#ddd;color:black}</style></head><body><nav><ul><li><a href="/">Home</a></li><li><a href="/logs">Logs</a></li><li><a href="/chatlog">Chatlog</a></li><li><a href="/console">Console</a></li><li><a href="/details">Details</a></li><li><a href="/battery-chart">Battery Chart</a></li></ul></nav><h2>Console Output (últimos 5 minutos)</h2><pre style="white-space:pre;font-family:monospace;overflow-x:auto;">{{ logs }}</pre><h2>📦 Fetched Growatt Data</h2><pre style="white-space:pre;font-family:monospace;overflow-x:auto;">{{ data }}</pre></body></html>
    """, logs="\n\n".join(m for _, m in console_logs), data=pprint.pformat(fetched_data, indent=2))

@app.route("/battery-chart", methods=["GET", "POST"])
def battery_chart():
    global last_successful_growatt_update_time
    selected_date = request.form.get("date") if request.method == "POST" else get_today_date_utc_minus_5()
    growatt_login2()
    battery_payload = {'plantId': PLANT_ID, 'storageSn': STORAGE_SN, 'date': selected_date}
    battery_data = {}
    try:
        battery_response = session.post('https://server.growatt.com/panel/storage/getStorageBatChart', headers=HEADERS, data=battery_payload, timeout=10)
        battery_response.raise_for_status()
        battery_data = battery_response.json()
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Failed to fetch battery data for {selected_date}: {e}")
    soc_data = battery_data.get("obj", {}).get("socChart", {}).get("capacity", [])
    soc_data = soc_data + [None] * (288 - len(soc_data))
    energy_payload = {"date": selected_date, "plantId": PLANT_ID, "storageSn": STORAGE_SN}
    energy_data = {}
    try:
        energy_response = session.post("https://server.growatt.com/panel/storage/getStorageEnergyDayChart", headers=HEADERS, data=energy_payload, timeout=10)
        energy_response.raise_for_status()
        energy_data = energy_response.json()
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Failed to fetch energy chart data for {selected_date}: {e}")
    energy_obj = energy_data.get("obj", {}).get("charts", {})
    energy_titles = energy_data.get("titles", [])
    def prepare_series(data_list, name, color):
        cleaned_data = [float(x) if (isinstance(x,(int,float)) or (isinstance(x,str) and x.replace('.','',1).isdigit())) else None for x in data_list]
        if not cleaned_data or all(x is None for x in cleaned_data): return None
        return {"name": name, "data": cleaned_data, "color": color, "fillOpacity": 0.2, "lineWidth": 1}
    energy_series = [
        prepare_series(energy_obj.get("ppv"), "Photovoltaic Output", "#FFEB3B"),
        prepare_series(energy_obj.get("userLoad"), "Load Consumption", "#9C27B0"),
        prepare_series(energy_obj.get("pacToUser"), "Imported from Grid", "#00BCD4"),
    ]
    energy_series = [s for s in energy_series if s and s['name'] != 'Exported to Grid']
    for series in energy_series:
        if series and series["data"]: series["data"] = series["data"] + [None] * (288 - len(series["data"]))
        elif series: series["data"] = [None] * 288
    return render_template("battery-chart.html", selected_date=selected_date, soc_data=soc_data,
        raw_json=battery_data, energy_titles=energy_titles, energy_series=energy_series,
        last_growatt_update=last_successful_growatt_update_time)

@app.route('/dn')
def download_logs():
    try:
        return send_file(data_file, as_attachment=True, download_name=data_file_name, mimetype="application/json")
    except Exception as e:
        log_message(f"❌ Error downloading file: {e}")
        return f"❌ Error downloading file: {e}", 500

@app.route("/trigger_github_sync", methods=["POST"])
def trigger_github_sync():
    log_message("Received request to manually trigger GitHub sync.")
    sync_thread = threading.Thread(target=_perform_single_github_sync_operation, args=(g_repo,), daemon=True) # Pass g_repo
    sync_thread.start()
    return redirect(url_for('charts_view'))

github_sync_thread = threading.Thread(target=sync_github_repo, daemon=True)
github_sync_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
