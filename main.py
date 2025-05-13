import pytz
from flask import Flask, render_template_string, jsonify, request
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

import os
import json

# File for saving data
data_file = "saved_data.json"

# Your 20 new entries
new_data = [
    {"timestamp": "2025-05-12 22:12:42", "vGrid": "118.4", "outPutVolt": "118.4", "activePower": "217", "capacity": "39"},
    {"timestamp": "2025-05-12 22:17:26", "vGrid": "117.8", "outPutVolt": "117.8", "activePower": "214", "capacity": "43"},
    {"timestamp": "2025-05-12 22:22:09", "vGrid": "118.2", "outPutVolt": "118.2", "activePower": "222", "capacity": "47"},
    {"timestamp": "2025-05-12 22:26:53", "vGrid": "118.6", "outPutVolt": "118.6", "activePower": "213", "capacity": "51"},
    {"timestamp": "2025-05-12 22:31:37", "vGrid": "118.2", "outPutVolt": "118.2", "activePower": "226", "capacity": "54"},
    {"timestamp": "2025-05-12 22:36:20", "vGrid": "119", "outPutVolt": "119", "activePower": "217", "capacity": "58"},
    {"timestamp": "2025-05-12 22:41:04", "vGrid": "119", "outPutVolt": "119", "activePower": "217", "capacity": "62"},
    {"timestamp": "2025-05-12 22:45:48", "vGrid": "118.8", "outPutVolt": "118.8", "activePower": "286", "capacity": "66"},
    {"timestamp": "2025-05-12 22:50:31", "vGrid": "119.4", "outPutVolt": "119.4", "activePower": "214", "capacity": "70"},
    {"timestamp": "2025-05-12 22:55:15", "vGrid": "120.4", "outPutVolt": "120.4", "activePower": "213", "capacity": "74"},
    {"timestamp": "2025-05-12 22:59:59", "vGrid": "120.1", "outPutVolt": "120.1", "activePower": "288", "capacity": "78"},
    {"timestamp": "2025-05-12 23:04:43", "vGrid": "120", "outPutVolt": "120", "activePower": "210", "capacity": "81"},
    {"timestamp": "2025-05-12 23:09:27", "vGrid": "120", "outPutVolt": "120", "activePower": "250", "capacity": "85"},
    {"timestamp": "2025-05-12 23:14:10", "vGrid": "120.3", "outPutVolt": "120.3", "activePower": "201", "capacity": "89"},
    {"timestamp": "2025-05-12 23:18:54", "vGrid": "122.6", "outPutVolt": "122.6", "activePower": "233", "capacity": "92"},
    {"timestamp": "2025-05-12 23:23:38", "vGrid": "122.6", "outPutVolt": "122.6", "activePower": "208", "capacity": "92"},
    {"timestamp": "2025-05-12 23:28:22", "vGrid": "122.5", "outPutVolt": "122.5", "activePower": "300", "capacity": "92"},
    {"timestamp": "2025-05-12 23:33:05", "vGrid": "123.1", "outPutVolt": "123.1", "activePower": "227", "capacity": "95"},
    {"timestamp": "2025-05-12 23:37:49", "vGrid": "122.8", "outPutVolt": "122.8", "activePower": "231", "capacity": "97"},
    {"timestamp": "2025-05-12 23:42:33", "vGrid": "124.2", "outPutVolt": "120.1", "activePower": "297", "capacity": "100"}
]

# Create or append to the JSON file
if not os.path.exists(data_file):
    # File doesn't exist, create it with new data
    with open(data_file, "w") as f:
        json.dump(new_data, f, indent=4)
    print("File created and data written.")
else:
    # File exists, read and append
    with open(data_file, "r") as f:
        try:
            existing_data = json.load(f)
            if not isinstance(existing_data, list):
                existing_data = []
        except json.JSONDecodeError:
            existing_data = []

    # Append new entries
    existing_data.extend(new_data)
    with open(data_file, "w") as f:
        json.dump(existing_data, f, indent=4)
    print("Data appended to existing file.")

# Credentials
username1 = "vospina"
password1 = "Vospina.2025"

# Telegram Config
TELEGRAM_TOKEN = "7653969082:AAGJ_8TL2-MA0uCLgtx8UAyfEBRwCmFWyzY"
CHAT_IDS = ["5715745951"]
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

def get_battery_data(date):
    payload = {
        'plantId': PLANT_ID,
        'storageSn': STORAGE_SN,
        'date': date
    }
    response = session.post('https://server.growatt.com/panel/storage/getStorageBatChart', headers=HEADERS, data=payload)
    return response.json()

def get_today_date_utc_minus_5():
    now = datetime.utcnow() - timedelta(hours=5)
    return now.strftime('%Y-%m-%d')

api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})

current_data = {}
last_update_time = "Never"
console_logs = []
updater = None

def log_message(message):
    timestamped = f"{(datetime.now() - timedelta(hours=5)).strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now = time.time()
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 300]

def send_telegram_message(message):
    for chat_id in CHAT_IDS:
        for attempt in range(3):
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                payload = {"chat_id": chat_id, "text": message}
                response = requests.post(url, data=payload, timeout=10)
                response.raise_for_status()
                log_message(f"✅ Message sent to {chat_id}")
                break
            except requests.exceptions.RequestException as e:
                log_message(f"❌ Attempt {attempt + 1} failed to send message to {chat_id}: {e}")
                time.sleep(5)
                if attempt == 2:
                    log_message(f"❌ Failed to send message to {chat_id} after 3 attempts")

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
        return None

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
        return None

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
        return None

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

monitor_thread = threading.Thread(target=monitor_growatt, daemon=True)
monitor_thread.start()

updater.start_polling()

# Flask Routes
@app.route("/")
def home():
    return render_template_string("""
        <html>
        <head>
            <title>Home - Growatt Monitor</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                    text-align: center;
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
                .content {
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }
                table {
                    margin: 0 auto;
                    border-collapse: collapse;
                }
                table th, table td {
                    padding: 8px 12px;
                    border: 1px solid #000;
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

            <div class="content">
                <h1>✅ Growatt Monitor is Running!</h1>
                <h2>Detalles del Inversor</h2>
                <h3>Información constante</h3>
                <p>Plant ID: {{ plant_id }}</p>
                <p>User ID: {{ user_id }}</p>
                <p>Inverter SN: {{ inverter_sn }}</p>
                <p>Datalogger SN: {{ datalog_sn }}</p>

                <h2>Datos en tiempo real</h2>
                <table>
                    <tr><th>AC Input Voltage</th><td>{{ d['ac_input_voltage'] }}</td></tr>
                    <tr><th>AC Input Frequency</th><td>{{ d['ac_input_frequency'] }}</td></tr>
                    <tr><th>AC Output Voltage</th><td>{{ d['ac_output_voltage'] }}</td></tr>
                    <tr><th>AC Output Frequency</th><td>{{ d['ac_output_frequency'] }}</td></tr>
                    <tr><th>Load Power</th><td>{{ d['load_power'] }}</td></tr>
                    <tr><th>Battery Capacity</th><td>{{ d['battery_capacity'] }}</td></tr>
                </table>
                <p><b>Última actualización:</b> {{ last }}</p>
            </div>
        </body>
        </html>
    """, d=current_data, last=last_update_time,
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

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Growatt Charts</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/luxon@3.4.3/build/global/luxon.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-luxon@1.3.1"></script>
        <style>
            body {
                font-family: Arial, sans-serif;
                background-color: #f9f9f9;
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
            h2 {
                text-align: center;
                margin: 20px;
            }
            canvas {
                display: block;
                margin: 30px auto;
                background: #fff;
                border: 1px solid #ccc;
                padding: 10px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
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

        <h2>Growatt Monitoring Charts (Last 24 Hours)</h2>
        <canvas id="acInputChart" width="1000" height="500"></canvas>
        <canvas id="acOutputChart" width="1000" height="500"></canvas>
        <canvas id="activePowerChart" width="1000" height="500"></canvas>
        <canvas id="batteryChart" width="1000" height="500"></canvas>

        <script>
            const labels = {{ timestamps | tojson }};
            const acInput = {{ ac_input | tojson }};
            const acOutput = {{ ac_output | tojson }};
            const activePower = {{ active_power | tojson }};
            const batteryCapacity = {{ battery_capacity | tojson }};

            function drawChart(id, label, data, color) {
    const transparentColor = {
        "blue": "rgba(0, 0, 255, 0.2)",
        "green": "rgba(0, 128, 0, 0.2)",
        "red": "rgba(255, 0, 0, 0.2)",
        "orange": "rgba(255, 165, 0, 0.2)"
    }[color] || color;

    new Chart(document.getElementById(id), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: data,
                borderColor: color,
                backgroundColor: transparentColor,
                fill: true,
                tension: 0.2
            }]
        },
        options: {
            responsive: false,
            maintainAspectRatio: false,
            scales: {
                x: {
                    type: 'time',
                    time: {
                        parser: 'yyyy-MM-dd HH:mm:ss',
                        unit: 'hour',
                        displayFormats: { hour: 'HH:mm' },
                        tooltipFormat: 'yyyy-MM-dd HH:mm'
                    },
                    ticks: {
                        autoSkip: true,
                        maxTicksLimit: 20,
                        font: {
                            weight: 'bold'
                        }
                    }
                },
                y: {
                    beginAtZero: false,
                    ticks: {
                        font: {
                            weight: 'bold'
                        }
                    }
                }
            }
        }
    });
}

            drawChart("acInputChart", "AC Input Voltage", acInput, "blue");
            drawChart("acOutputChart", "AC Output Voltage", acOutput, "green");
            drawChart("activePowerChart", "Active Power", activePower, "red");
            drawChart("batteryChart", "Battery Capacity", batteryCapacity, "orange");
        </script>
    </body>
    </html>
    """, timestamps=timestamps, ac_input=ac_input, ac_output=ac_output,
         active_power=active_power, battery_capacity=battery_capacity)
        
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
    raw_json = get_battery_data(selected_date)
    soc_data = raw_json.get("obj", {}).get("socChart", {}).get("capacity", [])
    soc_data = soc_data + [None] * (288 - len(soc_data))  # pad to 288 points

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Battery SoC Chart</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://code.highcharts.com/highcharts.js"></script>
        <style>
            html, body {
                width: 100%;
                overflow-x: hidden;
                font-family: sans-serif;
                margin: 0;
                padding: 0;
                text-align: center;
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
            nav ul li a.active {
                background-color: #04AA6D;
                color: white;
            }
            #controls {
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 20px;
                font-size: 24px;
                margin-top: 20px;
            }
            #controls input[type="date"] {
                font-size: 20px;
                padding: 4px;
            }
            button.arrow {
                font-size: 28px;
                background: none;
                border: none;
                cursor: pointer;
            }
            #chart-container {
                width: 100%;  /* Ensure the chart width scales to container */
                height: 500px;
                margin: 20px auto;
            }

            /* Media query for portrait/mobile view */
            @media (max-width: 768px) {
                #chart-container {
                    width: 800px;  /* Fix width on smaller screens */
                    height: 400px;  /* Reduce height for mobile */
                }
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
                <li><a href="/battery-chart" class="active">Battery Chart</a></li>
            </ul>
        </nav>

        <h2>Battery SoC Chart</h2>
        <form method="post" id="dateForm">
            <div id="controls">
                <button class="arrow" type="button" onclick="shiftDate(-1)">←</button>
                <input type="date" name="date" id="datePicker" value="{{ selected_date }}" required onchange="submitForm()">
                <button class="arrow" type="button" onclick="shiftDate(1)">→</button>
            </div>
        </form>

        <div id="chart-container"></div>

        <script>
            function submitForm() {
                document.getElementById('dateForm').submit();
            }

            function shiftDate(offset) {
                const picker = document.getElementById('datePicker');
                const current = new Date(picker.value);
                current.setDate(current.getDate() + offset);
                picker.valueAsDate = current;
                submitForm();
            }

            const socData = {{ soc_data | tojson }};
            const timeLabels = Array.from({ length: 288 }, (_, i) => {
                return Math.floor(i / 12).toString().padStart(2, '0');  // Show only hour labels
            });

            Highcharts.chart('chart-container', {
                chart: {
                    type: 'area',
                    spacingTop: 10,
                    spacingBottom: 10,
                    width: '100%',  // Adjust width for better responsiveness
                    height: 500,
                    animation: false
                },
                title: {
                    text: 'State of Charge on {{ selected_date }}',
                    style: {
                        fontWeight: 'bold',
                        fontSize: '24px'
                    }
                },
                xAxis: {
                    categories: timeLabels,
                    tickInterval: 12,  // Only label every 12th data point (i.e., every hour)
                    title: {
                        text: 'Hour',
                        style: {
                            fontWeight: 'bold',
                            fontSize: '18px'
                        }
                    },
                    labels: {
                        formatter: function () {
                            return this.pos % 12 === 0 ? timeLabels[this.pos] : '';  // Show label only for each hour (0, 1, ..., 23)
                        },
                        style: {
                            fontWeight: 'bold',
                            fontSize: '16px'
                        }
                    }
                },
                yAxis: {
                    min: 0,
                    max: 100,
                    title: {
                        text: 'SoC (%)',
                        style: {
                            fontWeight: 'bold',
                            fontSize: '18px'
                        }
                    },
                    labels: {
                        style: {
                            fontWeight: 'bold',
                            fontSize: '16px'
                        }
                    }
                },
                tooltip: {
                    shared: true,
                    style: {
                        fontWeight: 'bold',
                        fontSize: '16px'
                    },
                    formatter: function () {
                        const hour = Math.floor(this.points[0].point.index / 12).toString().padStart(2, '0');
                        const minute = ((this.points[0].point.index % 12) * 5).toString().padStart(2, '0');
                        return `Time: ${hour}:${minute}<br>SoC: ${this.points[0].y}%`;
                    }
                },
                plotOptions: {
                    area: {
                        fillOpacity: 0.2,
                        marker: {
                            enabled: false
                        }
                    },
                    series: {
                        lineWidth: 2
                    }
                },
                series: [{
                    name: 'SoC',
                    data: socData
                }],
                responsive: {
                    rules: []  // Disable automatic resizing
                }
            });
        </script>

    </body>
    </html>
    ''', soc_data=soc_data, selected_date=selected_date, raw_json=raw_json)



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
