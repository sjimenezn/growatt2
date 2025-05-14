
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

# File for saving data
data_file = "saved_data.json"

# Ensure the file exists before any read/write operations
if not os.path.exists(data_file):
    with open(data_file, "w") as f:
        pass  # Creates an empty file if it doesn't exist
# Credentials
username1 = "vospina"
password1 = "Vospina.2025"

# Telegram Config
TELEGRAM_TOKEN = "7653969082:AAGJ_8TL2-MA0uCLgtx8UAyfEBRwCmFWyzY"
CHAT_IDS = ["5715745951"]  # Only sends messages to 'sergiojim' chat ID
chat_log = set()

# Flask App
app = Flask(__name__)

GROWATT_USERNAME = "vospina"
PASSWORD_CRC = "0c4107c238d57d475d4660b07b2f043e"
STORAGE_SN = "BNG7CH806N"
PLANT_ID = "2817170"

HEADERS = {
    'User-Agent': 'Mozilla/5.0',
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
#aca iba el fetch the battery

def get_today_date_utc_minus_5():
    now = datetime.utcnow() - timedelta(hours=5)
    return now.strftime('%Y-%m-%d')


# Growatt API
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})

# Shared Data
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
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 300]


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

def save_data_to_file(data):
    try:
        if os.path.exists(data_file):
            with open(data_file, "r") as f:
                lines = f.readlines()
        else:
            lines = []

        lines.append(json.dumps(data) + "\n")
        lines = lines[-1000:]

        with open(data_file, "w") as f:
            f.writelines(lines)

        log_message("✅ Saved data to file.")
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
                if loop_counter >= 7:
                    data_to_save = {
                        "timestamp": last_update_time,
                        "vGrid": ac_input_v,
                        "outPutVolt": ac_output_v,
                        "activePower": load_w,
                        "capacity": battery_pct
                    }
                    save_data_to_file(data_to_save)
                    loop_counter = 0

                if ac_input_v != "N/A":
                    if float(ac_input_v) < threshold and not sent_lights_off:
                        time.sleep(110)
                        data = api.storage_detail(inverter_sn)
                        ac_input_v = data.get("vGrid", "N/A")
                        if float(ac_input_v) < threshold:
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
                        time.sleep(110)
                        data = api.storage_detail(inverter_sn)
                        ac_input_v = data.get("vGrid", "N/A")
                        if float(ac_input_v) >= threshold:
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
                user_id, plant_id, inverter_sn, datalog_sn = login_growatt()

            time.sleep(40)

    except Exception as e_outer:
        log_message(f"❌ Fatal error in monitor_growatt: {e_outer}")
# The rest of your code (Telegram handlers, Flask routes, etc.) remains unchanged

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

# Flask Routes
@app.route("/")
def home():
    return render_template("home.html",
        d=current_data,
        last=last_update_time,
        plant_id=current_data.get("plant_id", "N/A"),
        user_id=current_data.get("user_id", "N/A"),
        inverter_sn=current_data.get("inverter_sn", "N/A"),
        datalog_sn=current_data.get("datalog_sn", "N/A"))

@app.route("/logs")
def charts_view():
    try:
        # Read and parse the saved data
        with open(data_file, "r") as file:
            saved_data = file.readlines()
        parsed_data = [json.loads(line.strip()) for line in saved_data]
    except Exception as e:
        log_message(f"❌ Error reading saved data for charts: {e}")
        return "Error loading chart data.", 500

    # Filter entries from the last 24 hours
    now = datetime.now()
    last_24h = now - timedelta(hours=24)
    filtered_data = [
        entry for entry in parsed_data
        if datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S") >= last_24h
    ]

    timestamps = [entry['timestamp'] for entry in filtered_data]
    ac_input = [float(entry['vGrid']) for entry in filtered_data]
    ac_output = [float(entry['outPutVolt']) for entry in filtered_data]
    active_power = [int(entry['activePower']) for entry in filtered_data]
    battery_capacity = [int(entry['capacity']) for entry in filtered_data]

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
            <meta name="viewport" content="width=device-width, initial-scale=1">
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
            <meta name="viewport" content="width=device-width, initial-scale=1">
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

@app.route("/details")
def details_view():
    try:
        # Read the saved data from the file
        with open(data_file, "r") as file:
            saved_data = file.readlines()

        # Parse each line as a JSON object and prepare it for display
        parsed_data = [json.loads(line.strip()) for line in saved_data]

    except Exception as e:
        log_message(f"❌ Error reading saved data for details: {e}")
        return "Error loading details data.", 500

    # Display the details of the most recent entry
    latest_entry = parsed_data[-1] if parsed_data else {}
    return render_template_string("""
        <html>
        <head>
            <title>Growatt Details</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
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
            <h1>Details</h1>
            <h2>Latest Data</h2>
            <pre>{{ latest_entry }}</pre>
        </body>
        </html>
    """, latest_entry=latest_entry)

@app.route("/battery-chart", methods=["GET", "POST"])
def battery_chart():
    selected_date = request.form.get("date") if request.method == "POST" else get_today_date_utc_minus_5()

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

    if not energy_titles or not energy_obj:
        log_message(f"⚠️ No energy chart data received for {selected_date}")

    # Format each data series for Highcharts
    def prepare_series(data_list, name, color):
        if not data_list or not isinstance(data_list, list):
            return None
        return {
            "name": name,
            "data": data_list,
            "color": color,
            "fillOpacity": 0.2
        }

    energy_series = [
        prepare_series(energy_obj.get("ppv"), "Photovoltaic Output", "#30D3EB"),
        prepare_series(energy_obj.get("userLoad"), "Load Consumption", "#FB6E6C"),
        prepare_series(energy_obj.get("pacToUser"), "Imported from Grid", "#6370DE"),
    ]

    if "pacToGrid" in energy_obj:
        grid_series = prepare_series(energy_obj.get("pacToGrid"), "Exported to Grid", "#02a7f0")
        if grid_series:
            energy_series.append(grid_series)

    energy_series = [s for s in energy_series if s]

    return render_template(
        "battery-chart.html",
        selected_date=selected_date,
        soc_data=soc_data,
        raw_json=battery_data,
        energy_titles=energy_titles,
        energy_series=energy_series
    )

@app.route('/download-logs')
def download_logs():
    try:
        return send_file("saved_data.json", as_attachment=True, download_name="saved_data.json")
    except Exception as e:
        return f"❌ Error downloading file: {e}", 500

        
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
