from flask import Flask, render_template_string, jsonify
import threading
import pprint
import time
import requests
from datetime import datetime, timedelta
from growattServer import GrowattApi
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# Credentials
username = "vospina"
password = "Vospina.2025"

# Telegram Config
TELEGRAM_TOKEN = "7653969082:AAGrvPu_NtBqcaEy3KL7RwUt_8vHcR1hT3A"
CHAT_IDS = ["5715745951"]
chat_log = set()

# Flask App
app = Flask(__name__)

# Growatt API
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})

# Shared Data
current_data = {}
last_update_time = "Never"
console_logs = []
updater = None
fetched_data = {}

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

def login_growatt():
    log_message("🔄 Attempting Growatt login...")
    try:
        login_response = api.login(username, password)
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

    return user_id, plant_id, inverter_sn, datalog_sn

def monitor_growatt():
    global last_update_time
    threshold = 80
    sent_lights_off = False
    sent_lights_on = False

    try:
        user_id, plant_id, inverter_sn, datalog_sn = login_growatt()
        while True:
            try:
                data = api.storage_detail(inverter_sn)
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

                if ac_input_v != "N/A":
                    if float(ac_input_v) < threshold and not sent_lights_off:
                        time.sleep(110)
                        data = api.storage_detail(inverter_sn)
                        ac_input_v = data.get("vGrid", "N/A")
                        if float(ac_input_v) < threshold:
                            msg = f"""🔴🔴¡Se fue la luz en Acacías!🔴🔴

🕒 Hora: {last_update_time}
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

🕒 Hora: {last_update_time}
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

# Telegram bot handlers
def start(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    update.message.reply_text("¡Bienvenido al monitor Growatt! Usa /status para ver el estado del inversor.")

def send_status(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    timestamp = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
    msg = f"""🕒 Hora {timestamp} (UTC−5)
⚡ /status Estado del inversor

Nivel de batería: {current_data.get("battery_capacity", "N/A")} %
Voltaje de la red: {current_data.get("ac_input_voltage", "N/A")} V / {current_data.get("ac_input_frequency", "N/A")} Hz
Voltaje del inversor: {current_data.get("ac_output_voltage", "N/A")} V / {current_data.get("ac_output_frequency", "N/A")} Hz
Consumo actual: {current_data.get("load_power", "N/A")} W"""
    update.message.reply_text(msg)

def stop(update: Update, context: CallbackContext):
    chat_log.remove(update.effective_chat.id)
    update.message.reply_text("¡Adiós!")

# Flask Routes
@app.route("/")
def home():
    return render_template_string("""
    <h1>Growatt Monitoring System</h1>
    <p>Last update time: {{ last_update_time }}</p>
    <ul>
      <li>AC Input Voltage: {{ current_data.ac_input_voltage }} V</li>
      <li>AC Input Frequency: {{ current_data.ac_input_frequency }} Hz</li>
      <li>AC Output Voltage: {{ current_data.ac_output_voltage }} V</li>
      <li>AC Output Frequency: {{ current_data.ac_output_frequency }} Hz</li>
      <li>Load Power: {{ current_data.load_power }} W</li>
      <li>Battery Capacity: {{ current_data.battery_capacity }} %</li>
    </ul>
    """, current_data=current_data, last_update_time=last_update_time)

@app.route("/logs")
def logs():
    return render_template_string("""
    <h1>Console Logs</h1>
    <table border="1">
        <tr><th>Timestamp</th><th>Message</th></tr>
        {% for timestamp, message in console_logs %}
            <tr>
                <td>{{ timestamp }}</td>
                <td>{{ message }}</td>
            </tr>
        {% endfor %}
    </table>
    """, console_logs=console_logs)

@app.route("/chatlog")
def chatlog():
    return render_template_string("""
    <h1>Chat Log</h1>
    <ul>
        {% for chat_id in chat_log %}
            <li>{{ chat_id }}</li>
        {% endfor %}
    </ul>
    """, chat_log=chat_log)

@app.route("/console")
def console():
    return render_template_string("""
    <h1>Console Output</h1>
    <pre>{{ console_logs }}</pre>
    """, console_logs=pprint.pformat(console_logs))

@app.route("/details")
def details():
    return render_template_string("""
    <h1>Details</h1>
    <pre>{{ fetched_data }}</pre>
    """, fetched_data=pprint.pformat(fetched_data))

# Main Thread
if __name__ == '__main__':
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('status', send_status))
    dispatcher.add_handler(CommandHandler('stop', stop))

    threading.Thread(target=updater.start_polling, daemon=True).start()
    threading.Thread(target=app.run, kwargs={'debug': False, 'use_reloader': False, 'host': '0.0.0.0', 'port': 8000}, daemon=True).start()
    threading.Thread(target=monitor_growatt, daemon=True).start()

    while True:
        time.sleep(1)
