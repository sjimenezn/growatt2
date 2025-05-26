import pytz
from flask import Flask, render_template, render_template_string, jsonify, request, send_file
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
    print(f"Initialized empty data file: {data_file}") # Added for clarity on startup

# --- Credentials ---
username1 = "vospina"
password1 = "Vospina.2025"

# --- Telegram Config ---
TELEGRAM_TOKEN = "7653969082:AAGGuY6-sZz0KbVDTa0zfNanMF4MH1vP_oo"
CHAT_IDS = ["5715745951"]  # Only sends messages to 'sergiojim' chat ID
chat_log = set()

# --- Flask App ---
app = Flask(__name__)

GROWATT_USERNAME = "vospina"
PASSWORD_CRC = "0c4107c238d57d475d4660b07b2f043e"
STORAGE_SN = "BNG7CH806N"
PLANT_ID = "2817170"

HEADERS = {
    'User-Agent': 'Mozilla/5.5', # Updated user agent slightly
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
last_update_time = "Never"
console_logs = []
updater = None  # Global reference

def log_message(message):
    # Apply a 5-hour reduction to the timestamp
    timestamped = f"{(datetime.now() - timedelta(hours=5)).strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now = time.time()
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 6000]


def send_telegram_message(message):
    for chat_id in CHAT_IDS:
        for attempt in range(3):  # Retry up to 3 times
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                payload = {"chat_id": chat_id, "text": message}
                response = requests.post(url, data=payload, timeout=10)
                response.raise_for_status()  # Raise exception for HTTP errors
                log_message(f"✅ Message sent to {chat_id}")
                break  # Exit retry loop if successful
            except requests.exceptions.RequestException as e:
                log_message(f"❌ Attempt {attempt + 1} failed to send message to {chat_id}: {e}")
                time.sleep(5)  # Wait before retrying
                if attempt == 2:  # Final attempt failed
                    log_message(f"❌ Failed to send message to {chat_id} after 3 attempts")

# Global variable to hold the fetched data
fetched_data = {}

def login_growatt():
    log_message("🔄 Attempting Growatt login...")
    
    try:
        # Attempting to login and fetching the login response
        login_response = api.login(username1, password1)
        fetched_data['login_response'] = login_response  # Save login response
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
        return None

    try:
        # Fetching plant information
        plant_info = api.plant_list(user_id)
        fetched_data['plant_info'] = plant_info  # Save plant info
        plant_data = plant_info['data'][0]
        plant_id = plant_data['plantId']
        fetched_data['plant_id'] = plant_id  # Save plant ID
        fetched_data['plant_name'] = plant_data['plantName']
        fetched_data['plant_total_data'] = plant_info.get('totalData', {})
    except Exception as e:
        log_message(f"❌ Failed to retrieve plant info: {e}")
        return None

    try:
        # Fetching inverter information
        inverter_info = api.inverter_list(plant_id)
        fetched_data['inverter_info'] = inverter_info  # Save inverter info
        inverter_data = inverter_info[0]
        inverter_sn = inverter_data['deviceSn']
        datalog_sn = inverter_data.get('datalogSn', 'N/A')
        fetched_data['inverter_sn'] = inverter_sn  # Save inverter SN
        fetched_data['datalog_sn'] = datalog_sn  # Save datalogger SN
        fetched_data['inverter_alias'] = inverter_data.get('deviceAilas')
        fetched_data['inverter_capacity'] = inverter_data.get('capacity')
        fetched_data['inverter_energy'] = inverter_data.get('energy')
        fetched_data['inverter_active_power'] = inverter_data.get('activePower')
        fetched_data['inverter_apparent_power'] = inverter_data.get('apparentPower')
        fetched_data['inverter_status'] = inverter_data.get('deviceStatus')
    except Exception as e:
        log_message(f"❌ Failed to retrieve inverter info: {e}")
        return None

    try:
        # Fetching storage details
        storage_detail = api.storage_detail(inverter_sn)
        fetched_data['storage_detail'] = storage_detail  # Save full storage detail
    except Exception as e:
        log_message(f"❌ Failed to retrieve storage detail: {e}")
        fetched_data['storage_detail'] = {}

    # Log the fetched data
    log_message(f"🌿 User ID: {user_id}")
    log_message(f"🌿 Plant ID: {plant_id}")
    log_message(f"🌿 Inverter SN: {inverter_sn}")
    log_message(f"🌿 Datalogger SN: {datalog_sn}")

    # Return the gathered data
    return user_id, plant_id, inverter_sn, datalog_sn

# --- MODIFIED: save_data_to_file to save as JSON array ---
def save_data_to_file(data):
    try:
        existing_data = []
        # Check if the file exists and is not empty before trying to load
        if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
            with open(data_file, "r") as f:
                try:
                    existing_data = json.load(f)
                    # Ensure existing_data is a list; if not, wrap it in one
                    if not isinstance(existing_data, list):
                        log_message(f"⚠️ Warning: {data_file} did not contain a JSON list. Attempting to convert.")
                        existing_data = [existing_data]
                except json.JSONDecodeError:
                    # Fallback for old JSON Lines format or corruption: read line by line
                    f.seek(0) # Go back to the beginning of the file
                    lines = f.readlines()
                    existing_data = []
                    for line in lines:
                        stripped_line = line.strip()
                        if stripped_line:
                            try:
                                existing_data.append(json.loads(stripped_line))
                            except json.JSONDecodeError as e:
                                log_message(f"❌ Error decoding existing JSON line in {data_file}: {stripped_line} - {e}")
                                # Skip problematic line
        
        # Add the new data point
        existing_data.append(data)

        # Keep only the last 1200 entries (or your desired limit)
        existing_data = existing_data[-1200:]

        # Write the entire list back as a single JSON array
        with open(data_file, "w") as f:
            json.dump(existing_data, f, indent=None, separators=(',', ':')) # Compact output
            # For human-readable output in the file, use: json.dump(existing_data, f, indent=2)

        log_message("✅ Saved data to file as a JSON array.")
    except Exception as e:
        log_message(f"❌ Error saving data to file: {e}")

def monitor_growatt():
    global last_update_time
    threshold = 80
    sent_lights_off = False
    sent_lights_on = False

    loop_counter = 0

    try:
        user_id, plant_id, inverter_sn, datalog_sn = login_growatt()
        log_message("✅ Growatt login and initialization successful!")

        while True:
            try:
                data = api.storage_detail(inverter_sn)
                log_message(f"Growatt API data: {data}")

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

                last_update_time = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
                log_message(f"Updated current_data: {current_data}")

                loop_counter += 1
                if loop_counter >= 2: # Saves data every 7 cycles (approx 10 * 30s = 5 minutes)
                    data_to_save = {
                        "timestamp": last_update_time,
                        "vGrid": ac_input_v,
                        "outPutVolt": ac_output_v,
                        "activePower": load_w,
                        "capacity": battery_pct,
                        "freqOutPut": ac_output_f
                    }
                    save_data_to_file(data_to_save)
                    loop_counter = 0

                if ac_input_v != "N/A":
                    if float(ac_input_v) < threshold and not sent_lights_off:
                        time.sleep(110) # Wait a bit to confirm
                        data = api.storage_detail(inverter_sn) # Re-fetch to confirm
                        ac_input_v = data.get("vGrid", "N/A")
                        if float(ac_input_v) < threshold: # Confirm again
                            msg = f"""🔴🔴¡Se fue la luz en Acacías!🔴🔴
        🕒 Hora--> {last_update_time}
Nivel de batería      : {battery_pct} %
Voltaje de la red     : {ac_input_v} V / {ac_input_f} Hz
Voltaje del inversor: {ac_output_v} V / {ac_output_f} Hz
Consumo actual     : {load_w} W"""
                            send_telegram_message(msg)
                            sent_lights_off = True
                            sent_lights_on = False

                    elif float(ac_input_v) >= threshold and not sent_lights_on:
                        time.sleep(110) # Wait a bit to confirm
                        data = api.storage_detail(inverter_sn) # Re-fetch to confirm
                        ac_input_v = data.get("vGrid", "N/A")
                        if float(ac_input_v) >= threshold: # Confirm again
                            msg = f"""✅✅¡Llegó la luz en Acacías!✅✅
        🕒 Hora--> {last_update_time}
Nivel de batería      : {battery_pct} %
Voltaje de la red     : {ac_input_v} V / {ac_input_f} Hz
Voltaje del inversor: {ac_output_v} V / {ac_output_f} Hz
Consumo actual     : {load_w} W"""
                            send_telegram_message(msg)
                            sent_lights_on = True
                            sent_lights_off = False

            except Exception as e_inner:
                log_message(f"⚠️ Error during monitoring: {e_inner}")
                # Attempt to re-login on error to recover
                user_id, plant_id, inverter_sn, datalog_sn = login_growatt()

            time.sleep(30) # Wait for 30 seconds before next API call

    except Exception as e_outer:
        log_message(f"❌ Fatal error in monitor_growatt, restarting login: {e_outer}")
        # If login fails, try to re-login in the next loop iteration
        login_growatt() # This might be recursive, consider a simple return and let the outer loop restart

# --- Telegram Handlers ---
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

def stop_bot(update: Update, context: CallbackContext):
    update.message.reply_text("Bot detenido.")
    log_message("Bot detenido por comando /stop")
    updater.stop()

updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("status", send_status))
dp.add_handler(CommandHandler("chatlog", send_chatlog))
dp.add_handler(CommandHandler("stop", stop_bot))

# Start background monitoring thread
monitor_thread = threading.Thread(target=monitor_growatt, daemon=True)
monitor_thread.start()

# Start Telegram bot polling
updater.start_polling()

# --- Flask Routes ---
@app.route("/")
def home():
    return render_template("home.html",
        d=current_data,
        last=last_update_time,
        plant_id=current_data.get("plant_id", "N/A"),
        user_id=current_data.get("user_id", "N/A"),
        inverter_sn=current_data.get("inverter_sn", "N/A"),
        datalog_sn=current_data.get("datalog_sn", "N/A"))

# --- MODIFIED: /logs route to read JSON array ---
@app.route("/logs")
def charts_view():
    parsed_data = []
    # Check if file exists AND is not empty before trying to load
    if os.path.exists(data_file) and os.path.getsize(data_file) > 0: 
        try:
            with open(data_file, "r") as file:
                parsed_data = json.load(file) # Load the entire JSON array
            # Ensure parsed_data is a list; if file was empty or corrupted, it might be something else
            if not isinstance(parsed_data, list):
                log_message(f"❌ Data file {data_file} does not contain a JSON list. Resetting.")
                parsed_data = [] # Reset to empty list if not a list
        except json.JSONDecodeError as e:
            log_message(f"❌ Error decoding JSON from {data_file}: {e}. File might be corrupted.")
            parsed_data = [] # Clear data if decoding fails
        except Exception as e:
            log_message(f"❌ General error reading data for charts from {data_file}: {e}")
            parsed_data = []
    else:
        log_message(f"⚠️ Data file not found or empty: {data_file}. Charts will be empty.")
        # Ensure the file is created with an empty array if it doesn't exist or is invalid
        if not os.path.exists(data_file) or os.path.getsize(data_file) == 0:
            try:
                with open(data_file, "w") as f:
                    f.write("[]")
                log_message(f"Initialized empty data file: {data_file}")
            except Exception as e:
                log_message(f"❌ Error initializing empty data file: {e}")

    # Prepare timestamps as datetime objects for sorting and filtering
    processed_data = []
    for entry in parsed_data:
        # Ensure timestamp exists and is a string before attempting conversion
        if 'timestamp' in entry and isinstance(entry['timestamp'], str):
            try:
                entry['dt_timestamp'] = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
                processed_data.append(entry)
            except ValueError:
                log_message(f"Skipping entry with invalid timestamp format: {entry.get('timestamp')}")
        else:
            log_message(f"Skipping entry with missing or non-string timestamp: {entry}")


    # Sort data by timestamp (important for consistent slicing in JS)
    processed_data.sort(key=lambda x: x['dt_timestamp'])

    # Filter data to send a maximum of 96 hours to the frontend
    # This prevents sending excessively large datasets
    max_duration_hours_to_send = 96
    
    # Use the latest timestamp in the processed_data as 'now' for filtering,
    # if data exists. Otherwise, use actual current time.
    if processed_data:
        # Get the timestamp of the very last entry in your data
        # This makes the "last 24 hours" relative to your actual data, not the server's current time.
        reference_time = processed_data[-1]['dt_timestamp']
    else:
        # If no data is available, use the current time
        reference_time = datetime.now() 

    cutoff_time = reference_time - timedelta(hours=max_duration_hours_to_send)

    # Filter data to only include entries within the last `max_duration_hours_to_send`
    filtered_data_for_frontend = [
        entry for entry in processed_data
        if entry['dt_timestamp'] >= cutoff_time
    ]

    # Extract data - send original string timestamp for Highcharts
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
        print(f"Selected date on GET: {selected_date}")  # Add this line for debugging

    growatt_login2()

    # Request Battery SoC Data
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

    # Request Energy Chart Data
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

    # Access charts inside obj
    energy_obj = energy_data.get("obj", {}).get("charts", {})
    energy_titles = energy_data.get("titles", [])

    # Format each data series for Highcharts with updated line width and color
    def prepare_series(data_list, name, color):
        if not data_list or not isinstance(data_list, list) or not data_list: # Check if data_list is empty too
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

    # Ensure 288 data points for energy data
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
        # Send the saved_data.json file as an attachment
        return send_file(data_file, as_attachment=True, download_name="saved_data.json", mimetype="application/json")
    except Exception as e:
        log_message(f"❌ Error downloading file: {e}")
        return f"❌ Error downloading file: {e}", 500

        
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
