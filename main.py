from flask import Flask, render_template, render_template_string, jsonify, request, send_file, redirect, url_for, flash
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

# For GitHub Sync
import shutil
from git import Repo, GitCommandError

# --- File for saving data ---
data_file = "saved_data.json" # This is the file to be synced

# Ensure the file exists and is initialized as an empty JSON array
if not os.path.exists(data_file) or os.path.getsize(data_file) == 0:
    with open(data_file, "w") as f:
        f.write("[]")
    print(f"Initialized empty data file: {data_file}")

# --- Credentials ---
username1 = "vospina"
password1 = "Vospina.2025"

# --- Telegram Config ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN_GROWATT", "YOUR_FALLBACK_TOKEN_HERE") # Read from env var
CHAT_IDS = ["5715745951"]
chat_log = set()
telegram_enabled = False
updater = None
dp = None

# --- Flask App ---
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "a_super_secure_default_secret_key") # Needed for flash messages

# --- GitHub Sync Configuration ---
GITHUB_PAT = os.getenv("GITHUB_PAT")
# IMPORTANT: Ensure GITHUB_PAT is set in your Koyeb environment variables
GIT_REPO_URL_TEMPLATE = "https://{token}@github.com/sjimenezn/growatt2.git" # Your repo
GIT_REPO_DIR = "temp_growatt_repo" # Temporary directory for cloning
GIT_USER_NAME = "Koyeb Bot"
GIT_USER_EMAIL = "bot@koyeb.com"
GIT_COMMIT_MESSAGE = "Update Growatt data file (saved_data.json)"

# Growatt Constants (for secondary login/specific endpoints)
GROWATT_USERNAME = "vospina"
PASSWORD_CRC = "0c4107c238d57d475d4660b07b2f043e"
STORAGE_SN = "BNG7CH806N"
PLANT_ID = "2817170" # For battery-chart

HEADERS = {
    'User-Agent': 'Mozilla/5.5',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest'
}
session = requests.Session()

def growatt_login2():
    data = {
        'account': GROWATT_USERNAME, 'password': '', 'validateCode': '',
        'isReadPact': '0', 'passwordCrc': PASSWORD_CRC
    }
    try:
        response = session.post('https://server.growatt.com/login', headers=HEADERS, data=data, timeout=10)
        response.raise_for_status()
        # log_message("growatt_login2: Secondary login successful or session active.")
    except requests.exceptions.RequestException as e:
        log_message(f"growatt_login2: Secondary login failed: {e}")

def get_today_date_utc_minus_5():
    now = datetime.utcnow() - timedelta(hours=5)
    return now.strftime('%Y-%m-%d')

api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})

current_data = {}
last_processed_time = "Never"
last_logger_update_time_from_growatt = "N/A - Not yet fetched"
console_logs = []
fetched_data = {}

def log_message(message):
    timestamped = f"{(datetime.now() - timedelta(hours=5)).strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now_ts = time.time()
    console_logs[:] = [(t, m) for t, m in console_logs if now_ts - t < 300]

def safe_float(value, default_value=None):
    if value is None or value == "N/A": return default_value
    try: return float(value)
    except (ValueError, TypeError): return default_value

def safe_int(value, default_value=None):
    if value is None or value == "N/A": return default_value
    try: return int(float(value))
    except (ValueError, TypeError): return default_value

def send_telegram_message(message):
    global updater
    if telegram_enabled and updater and updater.running:
        for chat_id in CHAT_IDS:
            for attempt in range(3):
                try:
                    updater.bot.send_message(chat_id=chat_id, text=message)
                    log_message(f"✅ TG Message sent to {chat_id}")
                    break
                except Exception as e:
                    log_message(f"❌ TG Attempt {attempt + 1} failed: {e}")
                    time.sleep(5)
                    if attempt == 2: log_message(f"❌ Failed TG send to {chat_id}")
    # else: (logging for not enabled/running can be verbose, consider conditional logging)

def login_growatt():
    # (This function remains largely the same as your last version, ensuring it returns:
    # user_id, plant_id_val, inverter_sn, datalog_sn or None for failures)
    # For brevity, I'll skip pasting its full content here but assume it's the robust one.
    # Ensure fetched_data is updated within it.
    log_message("🔄 Attempting Growatt login (main API)...")
    try:
        login_response = api.login(username1, password1)
        fetched_data['login_response'] = login_response
        user = login_response.get('user', {})
        user_id = user.get('id')
        fetched_data['user_id'] = user_id # etc. for other fetched_data keys
        if not user_id:
            log_message("❌ Main API Login failed: No user ID.")
            return None, None, None, None
        log_message("✅ Main API Login successful!")

        plant_info = api.plant_list(user_id)
        fetched_data['plant_info'] = plant_info
        if not plant_info.get('data') or not plant_info['data'][0]:
            log_message("❌ No plant data found.")
            return user_id, None, None, None
        plant_data = plant_info['data'][0]
        plant_id_val = plant_data['plantId']
        fetched_data['plant_id'] = plant_id_val

        inverter_info_list = api.inverter_list(plant_id_val)
        fetched_data['inverter_info_list'] = inverter_info_list
        if not inverter_info_list or not isinstance(inverter_info_list, list) or len(inverter_info_list) == 0:
            log_message("❌ No inverter data found.")
            return user_id, plant_id_val, None, None
        inverter_data = inverter_info_list[0]
        inverter_sn = inverter_data['deviceSn']
        datalog_sn = inverter_data.get('datalogSn', 'N/A')
        fetched_data['inverter_sn'] = inverter_sn
        fetched_data['datalog_sn'] = datalog_sn

        log_message(f"🌿 Login OK: User {user_id}, Plant {plant_id_val}, Inv {inverter_sn}")
        return user_id, plant_id_val, inverter_sn, datalog_sn

    except Exception as e:
        log_message(f"❌ Main API Login or info retrieval sequence failed: {e}")
        return None, None, None, None


def save_data_to_file(data_to_save_val):
    # (This function remains the same as your last robust version)
    try:
        existing_data = []
        if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
            with open(data_file, "r") as f:
                try:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        existing_data = []
                except json.JSONDecodeError: # Fallback for line-by-line
                    f.seek(0); lines = f.readlines(); existing_data = []
                    for line in lines:
                        stripped = line.strip()
                        if stripped:
                            try: existing_data.append(json.loads(stripped))
                            except: pass # Skip bad lines silently or log
        existing_data.append(data_to_save_val)
        existing_data = existing_data[-1200:]
        with open(data_file, "w") as f:
            json.dump(existing_data, f, indent=None, separators=(',', ':'))
        # log_message("✅ Saved data to file.") # Can be too verbose
    except Exception as e:
        log_message(f"❌ Error saving data to file: {e}")


def get_logger_last_update_from_growatt(dynamic_plant_id):
    # (This function remains largely the same, ensuring growatt_login2() is called)
    # Ensure it updates global last_logger_update_time_from_growatt and returns fetched time or None
    global last_logger_update_time_from_growatt
    url = "https://server.growatt.com/panel/getDevicesByPlantList"
    payload = {'currPage': 1, 'plantId': dynamic_plant_id}
    try:
        growatt_login2()
        response = session.post(url, headers=HEADERS, data=payload, timeout=10)
        response.raise_for_status()
        data_resp = response.json()
        if data_resp.get("result") == 1 and data_resp.get("obj") and data_resp["obj"].get("datas"):
            if data_resp["obj"]["datas"]:
                logger_data = data_resp["obj"]["datas"][0]
                if "lastUpdateTime" in logger_data:
                    fetched_time = logger_data["lastUpdateTime"]
                    last_logger_update_time_from_growatt = fetched_time
                    return fetched_time
        log_message(f"⚠️ Logger time not found in API resp: {data_resp}")
    except Exception as e:
        log_message(f"❌ Error fetching logger last update: {e}")
    last_logger_update_time_from_growatt = "N/A - Fetch Failed"
    return None

def monitor_growatt():
    # (This function remains largely the same as your last robust version, with the power outage logic)
    # For brevity, I'll skip pasting its full content here.
    # Key elements:
    # - Loop to get dyn_user_id, dyn_plant_id, etc. from login_growatt()
    # - Calls api.storage_detail()
    # - Calls get_logger_last_update_from_growatt()
    # - Updates current_data
    # - Saves data with save_data_to_file()
    # - Handles Telegram alerts if telegram_enabled
    global last_processed_time, current_data
    threshold_v = 80; sent_lights_off = False; sent_lights_on = True; loop_counter = 0
    dyn_user_id, dyn_plant_id, dyn_inverter_sn, dyn_datalog_sn = None, None, None, None

    while True:
        try:
            if not all([dyn_user_id, dyn_plant_id, dyn_inverter_sn, dyn_datalog_sn]):
                dyn_user_id, dyn_plant_id, dyn_inverter_sn, dyn_datalog_sn = login_growatt()
                if not all([dyn_user_id, dyn_plant_id, dyn_inverter_sn, dyn_datalog_sn]):
                    log_message("Monitor: Growatt ID fetch failed. Retrying in 60s."); time.sleep(60); continue
            
            inverter_api_data = api.storage_detail(dyn_inverter_sn)
            get_logger_last_update_from_growatt(dyn_plant_id) # Updates global

            # Update current_data (example fields)
            current_data.update({
                "ac_input_voltage": inverter_api_data.get("vGrid", "N/A"),
                "battery_capacity": inverter_api_data.get("capacity", "N/A"),
                "load_power": inverter_api_data.get("activePower", "N/A"),
                "ac_input_frequency": inverter_api_data.get("freqGrid", "N/A"),
                "ac_output_voltage": inverter_api_data.get("outPutVolt", "N/A"),
                "ac_output_frequency": inverter_api_data.get("freqOutPut", "N/A"),
                "plant_id": dyn_plant_id, "user_id": dyn_user_id, 
                "inverter_sn": dyn_inverter_sn, "datalog_sn": dyn_datalog_sn
            })
            last_processed_time = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")

            loop_counter += 1
            if loop_counter >= 7:
                ts_save = last_logger_update_time_from_growatt if "N/A" not in last_logger_update_time_from_growatt else last_processed_time
                data_to_save = {
                    "timestamp": ts_save, "vGrid": current_data["ac_input_voltage"], 
                    "outPutVolt": current_data["ac_output_voltage"], "activePower": current_data["load_power"],
                    "capacity": current_data["battery_capacity"], "freqOutPut": current_data["ac_output_frequency"]
                }
                save_data_to_file(data_to_save); loop_counter = 0
            
            # Telegram alert logic
            if telegram_enabled and current_data["ac_input_voltage"] != "N/A":
                ac_v = 0.0
                try: ac_v = float(current_data["ac_input_voltage"])
                except: pass # Default to 0.0

                if ac_v < threshold_v and not sent_lights_off:
                    time.sleep(110) # Debounce
                    confirm_data = api.storage_detail(dyn_inverter_sn)
                    confirm_v_str = confirm_data.get("vGrid", "N/A")
                    confirm_v = 0.0
                    try: confirm_v = float(confirm_v_str if confirm_v_str != "N/A" else "0")
                    except: pass
                    if confirm_v < threshold_v:
                        msg = f"🔴🔴¡Se fue la luz!🔴🔴\n🕒L: {last_logger_update_time_from_growatt}\nBat: {current_data['battery_capacity']}%\nRed: {confirm_v_str}V\nCons: {current_data['load_power']}W"
                        send_telegram_message(msg); sent_lights_off=True; sent_lights_on=False
                elif ac_v >= threshold_v and not sent_lights_on:
                    if sent_lights_off: # Only notify if it was previously off
                        time.sleep(110) # Debounce
                        confirm_data = api.storage_detail(dyn_inverter_sn)
                        confirm_v_str = confirm_data.get("vGrid", "N/A")
                        confirm_v = threshold_v # Default to make it seem like it's back if "N/A"
                        try: confirm_v = float(confirm_v_str if confirm_v_str != "N/A" else str(threshold_v))
                        except: pass
                        if confirm_v >= threshold_v:
                            msg = f"✅✅¡Llegó la luz!✅✅\n🕒L: {last_logger_update_time_from_growatt}\nBat: {current_data['battery_capacity']}%\nRed: {confirm_v_str}V\nCons: {current_data['load_power']}W"
                            send_telegram_message(msg); sent_lights_on=True; sent_lights_off=False
                    else: # Ensure initial state is "on" without sending message if never off
                        sent_lights_on=True; sent_lights_off=False
        except Exception as e_monitor:
            log_message(f"⚠️ Major error in monitor_growatt: {e_monitor}")
            dyn_user_id, dyn_plant_id, dyn_inverter_sn, dyn_datalog_sn = None, None, None, None
            time.sleep(30)
        time.sleep(40)


def initialize_telegram_bot():
    # (This function remains largely the same, ensuring robust start/stop and token handling)
    # For brevity, I'll skip pasting its full content here. It should return True on success, False on failure.
    global updater, dp, TELEGRAM_TOKEN, telegram_enabled
    if not TELEGRAM_TOKEN or len(TELEGRAM_TOKEN) < 20:
        log_message(f"❌ TG Bot: Token missing or invalid: '{TELEGRAM_TOKEN}'.")
        telegram_enabled = False; return False
    if updater and updater.running:
        log_message("TG Bot is already running."); telegram_enabled = True; return True
    try:
        log_message("Initializing Telegram bot...");
        updater = Updater(token=TELEGRAM_TOKEN, use_context=True); dp = updater.dispatcher
        dp.add_handler(CommandHandler("start", start_command)) # Ensure these handlers are defined
        dp.add_handler(CommandHandler("status", send_status_command))
        dp.add_handler(CommandHandler("chatlog", send_chatlog_command))
        dp.add_handler(CommandHandler("stop", stop_bot_telegram_command))
        updater.start_polling()
        log_message("✅ TG Bot polling started."); return True
    except Exception as e:
        log_message(f"❌ Error starting TG Bot: {e}"); telegram_enabled = False; return False

# Telegram Command Handlers (ensure these are defined)
def start_command(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    update.message.reply_text("¡Bienvenido al monitor Growatt! Usa /status para ver el estado.")
def send_status_command(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    msg = f"⚡ Estado Inversor:\n🕒 App: {last_processed_time}\n🕒 Logger: {last_logger_update_time_from_growatt}\n" \
          f"Red: {current_data.get('ac_input_voltage', 'N/A')}V\n" \
          f"Bat: {current_data.get('battery_capacity', 'N/A')}%\n" \
          f"Consumo: {current_data.get('load_power', 'N/A')}W"
    update.message.reply_text(msg)
def send_chatlog_command(update: Update, context: CallbackContext):
    ids = "\n".join(str(cid) for cid in sorted(list(chat_log)))
    update.message.reply_text(f"IDs registrados:\n{ids if ids else 'Ninguno'}")
def stop_bot_telegram_command(update: Update, context: CallbackContext):
    global telegram_enabled, updater
    update.message.reply_text("Comando /stop recibido. Intentando detener el bot...")
    if telegram_enabled and updater and updater.running:
        updater.stop(); telegram_enabled = False
        log_message("TG Bot stopped via /stop command.")
        update.message.reply_text("Bot detenido.")
    else: update.message.reply_text("Bot no estaba activo.")


monitor_thread = threading.Thread(target=monitor_growatt, daemon=True)
monitor_thread.start()
log_message("Growatt monitoring thread started.")

# --- Flask Routes ---
@app.route("/")
def home():
    displayed_token = "Not Set"
    if TELEGRAM_TOKEN and len(TELEGRAM_TOKEN) > 10:
        displayed_token = TELEGRAM_TOKEN[:5] + "..." + TELEGRAM_TOKEN[-5:]
    return render_template("home.html",
                           d=current_data,
                           last_growatt_update=last_logger_update_time_from_growatt,
                           plant_id=current_data.get("plant_id", "N/A"),
                           user_id=current_data.get("user_id", "N/A"),
                           inverter_sn=current_data.get("inverter_sn", "N/A"),
                           datalog_sn=current_data.get("datalog_sn", "N/A"),
                           telegram_status="Running" if telegram_enabled and updater and updater.running else "Stopped",
                           current_telegram_token=displayed_token)

@app.route("/toggle_telegram", methods=["POST"])
def toggle_telegram():
    global telegram_enabled
    action = request.form.get('action')
    if action == 'start':
        if not (updater and updater.running):
            if initialize_telegram_bot():
                telegram_enabled = True; flash("Telegram bot started successfully!", "success")
            else:
                telegram_enabled = False; flash("Failed to start Telegram bot. Check logs and token.", "error")
        else:
            telegram_enabled = True; flash("Telegram bot is already running.", "info")
    elif action == 'stop':
        if updater and updater.running:
            updater.stop(); telegram_enabled = False
            flash("Telegram bot stopped.", "success")
        else:
            telegram_enabled = False; flash("Telegram bot was not running.", "info")
    return redirect(url_for('home'))

@app.route("/update_telegram_token", methods=["POST"])
def update_telegram_token():
    global TELEGRAM_TOKEN, telegram_enabled, updater, dp
    new_token = request.form.get('new_telegram_token', "").strip()
    if not new_token or len(new_token) < 20: # Basic validation
        flash("Invalid or missing new Telegram token.", "error")
        return redirect(url_for('home'))
    if updater and updater.running:
        updater.stop(); time.sleep(1) # Give it a moment
    updater = None; dp = None; telegram_enabled = False # Reset
    TELEGRAM_TOKEN = new_token
    if initialize_telegram_bot():
        telegram_enabled = True
        flash(f"Telegram token updated. Bot restarted with token: {TELEGRAM_TOKEN[:5]}...", "success")
    else:
        telegram_enabled = False
        flash("Failed to restart Telegram bot with new token. Check logs.", "error")
    return redirect(url_for('home'))

@app.route("/trigger_github_sync", methods=["POST"])
def trigger_github_sync():
    if not GITHUB_PAT:
        log_message("❌ GitHub Sync: GITHUB_PAT environment variable not set.")
        flash("GitHub Personal Access Token (GITHUB_PAT) is not configured on the server.", "error")
        return redirect(url_for('logs'))

    repo_url_with_token = GIT_REPO_URL_TEMPLATE.format(token=GITHUB_PAT)
    
    # Ensure data file exists before trying to sync
    if not os.path.exists(data_file):
        log_message(f"❌ GitHub Sync: Data file '{data_file}' not found.")
        flash(f"Data file '{data_file}' not found for syncing.", "error")
        return redirect(url_for('logs'))

    # Clean up previous temp repo if it exists
    if os.path.exists(GIT_REPO_DIR):
        log_message(f"Cleaning up old temporary repository: {GIT_REPO_DIR}")
        try:
            shutil.rmtree(GIT_REPO_DIR)
        except Exception as e_rm:
            log_message(f"❌ GitHub Sync: Error removing old temp repo: {e_rm}")
            flash(f"Error cleaning up old temp repo: {e_rm}", "error")
            return redirect(url_for('logs'))
            
    try:
        log_message(f"GitHub Sync: Cloning {GIT_REPO_URL_TEMPLATE.split('@')[-1]} into {GIT_REPO_DIR}...")
        repo = Repo.clone_from(repo_url_with_token, GIT_REPO_DIR)
        
        # Configure Git identity
        with repo.config_writer() as cw:
            cw.set_value("user", "name", GIT_USER_NAME)
            cw.set_value("user", "email", GIT_USER_EMAIL)
        log_message("GitHub Sync: Git user identity configured.")

        # Copy the data file to the repository
        # data_file is "saved_data.json"
        destination_file_path = os.path.join(GIT_REPO_DIR, os.path.basename(data_file))
        shutil.copy(data_file, destination_file_path)
        log_message(f"GitHub Sync: Copied '{data_file}' to '{destination_file_path}'.")

        # Add, commit, and push
        repo.index.add([os.path.basename(data_file)]) # Add by basename within the repo
        log_message("GitHub Sync: File added to index.")
        
        commit = repo.index.commit(GIT_COMMIT_MESSAGE)
        log_message(f"GitHub Sync: Committed with message '{GIT_COMMIT_MESSAGE}'. SHA: {commit.hexsha}")
        
        origin = repo.remote(name='origin')
        push_info = origin.push()
        
        # Check push success (push_info is a list of PushInfo objects)
        if push_info and all(p.flags & (p.ERROR | p.REJECTED) == 0 for p in push_info):
            log_message("✅ GitHub Sync: File pushed successfully!")
            flash("Data successfully synced to GitHub!", "success")
        else:
            log_message(f"❌ GitHub Sync: Push failed or had errors. PushInfo: {push_info}")
            # Attempt to get more detailed error if available
            error_details = "Unknown push error."
            if push_info and push_info[0].summary:
                 error_details = push_info[0].summary
            flash(f"GitHub sync: Push failed. {error_details}", "error")

    except GitCommandError as e_git:
        log_message(f"❌ GitHub Sync: GitCommandError: {e_git.stderr}")
        flash(f"GitHub Sync Git error: {e_git.stderr}", "error")
    except Exception as e:
        log_message(f"❌ GitHub Sync: An unexpected error occurred: {str(e)}")
        flash(f"GitHub Sync an unexpected error occurred: {str(e)}", "error")
    finally:
        # Clean up the temporary repository directory
        if os.path.exists(GIT_REPO_DIR):
            log_message(f"GitHub Sync: Cleaning up temporary repository: {GIT_REPO_DIR}")
            try:
                shutil.rmtree(GIT_REPO_DIR)
            except Exception as e_cleanup:
                log_message(f"❌ GitHub Sync: Error cleaning up temp repo: {e_cleanup}")
                # Not flashing here as the primary operation might have succeeded/failed already

    return redirect(url_for('logs'))


@app.route("/logs")
def charts_view():
    parsed_data = []
    if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
        try:
            with open(data_file, "r") as file: parsed_data = json.load(file)
            if not isinstance(parsed_data, list): parsed_data = []
        except: parsed_data = [] # Simplified error handling for brevity
    
    processed_data = []
    for entry in parsed_data:
        if 'timestamp' in entry and isinstance(entry['timestamp'], str):
            try:
                ts_str = entry['timestamp']
                if len(ts_str) == 10: ts_str += " 00:00:00"
                entry['dt_timestamp'] = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                processed_data.append(entry)
            except ValueError: pass # Skip invalid timestamps

    processed_data.sort(key=lambda x: x['dt_timestamp'])
    max_hours = 96
    ref_time = processed_data[-1]['dt_timestamp'] if processed_data else datetime.now() - timedelta(hours=5)
    cutoff = ref_time - timedelta(hours=max_hours)
    filtered_data = [e for e in processed_data if e['dt_timestamp'] >= cutoff]

    timestamps = [e['timestamp'] for e in filtered_data]
    ac_input = [safe_float(e.get('vGrid')) for e in filtered_data]
    ac_output = [safe_float(e.get('outPutVolt')) for e in filtered_data]
    active_power = [safe_int(e.get('activePower')) for e in filtered_data]
    battery_capacity = [safe_int(e.get('capacity')) for e in filtered_data]

    return render_template("logs.html",
                           timestamps=timestamps, ac_input=ac_input, ac_output=ac_output,
                           active_power=active_power, battery_capacity=battery_capacity,
                           last_growatt_update=last_logger_update_time_from_growatt) # Added this

@app.route("/chatlog")
def chatlog_view():
    return render_template_string("""<html><head><title>Chatlog</title><meta name="viewport" content="width=device-width, initial-scale=0.6"><style>body{font-family:Arial,sans-serif;margin:0;padding:0}nav{background-color:#333;overflow:hidden;position:sticky;top:0;z-index:100}nav ul{list-style-type:none;margin:0;padding:0;display:flex;justify-content:center}nav ul li{padding:14px 20px}nav ul li a{color:white;text-decoration:none;font-size:18px}nav ul li a:hover{background-color:#ddd;color:black}</style></head><body><nav><ul><li><a href="/">Home</a></li><li><a href="/logs">Logs</a></li><li><a href="/chatlog">Chatlog</a></li><li><a href="/console">Console</a></li><li><a href="/battery-chart">Battery Chart</a></li></ul></nav><h1>Chatlog</h1><pre>{{ chat_log_display }}</pre></body></html>""", chat_log_display="\n".join(str(cid) for cid in sorted(list(chat_log))))

@app.route("/console")
def console_view():
    return render_template_string("""<html><head><title>Console</title><meta name="viewport" content="width=device-width, initial-scale=0.6"><style>body{font-family:Arial,sans-serif;margin:0;padding:0}nav{background-color:#333;overflow:hidden;position:sticky;top:0;z-index:100}nav ul{list-style-type:none;margin:0;padding:0;display:flex;justify-content:center}nav ul li{padding:14px 20px}nav ul li a{color:white;text-decoration:none;font-size:18px}nav ul li a:hover{background-color:#ddd;color:black}</style></head><body><nav><ul><li><a href="/">Home</a></li><li><a href="/logs">Logs</a></li><li><a href="/chatlog">Chatlog</a></li><li><a href="/console">Console</a></li><li><a href="/battery-chart">Battery Chart</a></li></ul></nav><h2>Console (5min)</h2><pre style="white-space:pre-wrap;font-family:monospace;overflow-x:auto;word-wrap:break-word">{{ logs }}</pre><h2>Fetched Data</h2><pre style="white-space:pre-wrap;font-family:monospace;overflow-x:auto;word-wrap:break-word">{{ data }}</pre></body></html>""",
    logs="\n".join(m for _, m in console_logs),
    data=pprint.pformat(fetched_data, indent=2, width=120))

@app.route("/battery-chart", methods=["GET", "POST"])
def battery_chart():
    # (This function remains the same as the last robust version that fixed the Undefined error)
    # For brevity, I'll skip pasting its full content here.
    # Key: it should pass `energy_series=energy_series` to render_template.
    if request.method == "POST": selected_date = request.form.get("date")
    else: selected_date = get_today_date_utc_minus_5()
    log_message(f"Battery chart date: {selected_date}")
    growatt_login2()
    battery_data={}; soc_data_raw=[]; energy_data={}; energy_series=[]
    try: # SoC Data
        b_payload = {'plantId':PLANT_ID,'storageSn':STORAGE_SN,'date':selected_date}
        b_resp = session.post('https://server.growatt.com/panel/storage/getStorageBatChart', headers=HEADERS,data=b_payload,timeout=15)
        b_resp.raise_for_status(); battery_data=b_resp.json()
        soc_data_raw = battery_data.get("obj",{}).get("socChart",{}).get("capacity",[])
        if not isinstance(soc_data_raw,list): soc_data_raw=[]
    except Exception as e_bsoc: log_message(f"❌ BatSoC Err: {e_bsoc}")
    soc_padded = soc_data_raw + [None]*(288-len(soc_data_raw))
    try: # Energy Data
        e_payload = {"date":selected_date,"plantId":PLANT_ID,"storageSn":STORAGE_SN}
        e_resp = session.post("https://server.growatt.com/panel/storage/getStorageEnergyDayChart",headers=HEADERS,data=e_payload,timeout=15)
        e_resp.raise_for_status(); energy_data=e_resp.json()
        e_obj = energy_data.get("obj",{}).get("charts",{})
        if not isinstance(e_obj,dict): e_obj={}
        def prep_s(dl,n,c): cur_dl=dl if isinstance(dl,list) else []; pad_d=cur_dl+[None]*(288-len(cur_dl)); return{"name":n,"data":pad_d,"color":c,"fillOpacity":0.2,"lineWidth":1}
        tmp_es=[prep_s(e_obj.get("ppv"),"PV Output","#FFEB3B"), prep_s(e_obj.get("userLoad"),"Load","#9C27B0"), prep_s(e_obj.get("pacToUser"),"Import Grid","#00BCD4")]
        energy_series = [s for s in tmp_es if s] # Basic filter
    except Exception as e_beng: log_message(f"❌ BatEng Err: {e_beng}")
    return render_template("battery-chart.html", selected_date=selected_date, soc_data=soc_padded,
                           raw_json_battery=battery_data, raw_json_energy=energy_data, energy_series=energy_series)


@app.route('/dn')
def download_logs():
    try:
        return send_file(data_file, as_attachment=True, download_name="growatt_sensor_data.json", mimetype="application/json")
    except Exception as e:
        log_message(f"❌ Error downloading data: {e}")
        return f"❌ Error: {e}", 500

if __name__ == '__main__':
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_FALLBACK_TOKEN_HERE":
        log_message("⚠️ WARNING: Telegram token is not set or is using fallback. Bot features may be limited/disabled.")
    if not GITHUB_PAT:
        log_message("⚠️ WARNING: GITHUB_PAT is not set. GitHub sync feature will be disabled.")
    log_message("Starting Flask application...")
    app.run(host='0.0.0.0', port=8000) # Set debug=True for development if needed, False for prod

