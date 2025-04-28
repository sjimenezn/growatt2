from flask import Flask, render_template_string, jsonify
import threading
import time
import requests
import datetime
from growattServer import GrowattApi
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# Credentials
username = "vospina"
password = "Vospina.2025"

# Telegram Config
TELEGRAM_TOKEN = "7653969082:AAGJ5_P23E6SbkJnTSHOjHhUGlKwcE_hao8"
CHAT_IDS = ["5715745951", "7862573365"]  # Both users

# Setup Flask app
app = Flask(__name__)

# Setup Growatt API
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})

# Logs storage
current_data = {}
last_update_time = "Never"
logs = []

# Function to send message to Telegram
def send_telegram_message(message):
    for chat_id in CHAT_IDS:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        try:
            requests.post(url, data=payload, timeout=10)
        except Exception as e:
            print(f"❌ Failed to send Telegram message: {e}")
            logs.append(f"❌ Failed to send Telegram message: {e}")

# Function to log messages
def log_message(message):
    print(message)
    logs.append(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}")
    # Keep logs list from growing forever
    if len(logs) > 2000:
        del logs[:1000]

# Function to login to Growatt and fetch the inverter SN
def login_growatt():
    log_message("🔄 Attempting Growatt login...")
    login_response = api.login(username, password)
    plant_info = api.plant_list(login_response['user']['id'])
    plant_id = plant_info['data'][0]['plantId']
    inverter_info = api.inverter_list(plant_id)
    inverter_sn = inverter_info[0]['deviceSn']
    log_message(f"🌿 User ID: {login_response['user']['id']}")
    log_message(f"🌿 Plant ID: {plant_id}")
    return inverter_sn

# Function to monitor Growatt data
def monitor_growatt():
    global last_update_time
    ac_input_threshold = 115
    sent_lights_off = False
    sent_lights_on = False

    try:
        inverter_sn = login_growatt()
        log_message("✅ Growatt login and initialization successful!")

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
                    "battery_capacity": battery_pct
                })

                last_update_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                message = f"""\
AC INPUT: {ac_input_v} V / {ac_input_f} Hz
AC OUTPUT: {ac_output_v} V / {ac_output_f} Hz
Household load: {load_w} W
Battery %: {battery_pct}"""

                log_message(f"Updated Data: {current_data}")
                log_message(message)

                if ac_input_v != "N/A":
                    if float(ac_input_v) < ac_input_threshold and not sent_lights_off:
                        telegram_message = f"""⚠️ ¡Se fue la luz en Acacías! ⚠️

Nivel de bateria: {battery_pct} %

Voltaje de la red: {ac_input_v} V / {ac_input_f} Hz
Voltaje Inversor : {ac_output_v} V / {ac_output_f} Hz

Consumo Actual: {load_w} W"""
                        send_telegram_message(telegram_message)
                        send_telegram_message(telegram_message)
                        sent_lights_off = True
                        sent_lights_on = False

                    elif float(ac_input_v) >= ac_input_threshold and not sent_lights_on:
                        telegram_message = f"""⚠️ ¡Llegó la luz en Acacías! ⚠️

Nivel de bateria: {battery_pct} %

Voltaje de la red: {ac_input_v} V / {ac_input_f} Hz
Voltaje Inversor : {ac_output_v} V / {ac_output_f} Hz

Consumo Actual: {load_w} W"""
                        send_telegram_message(telegram_message)
                        send_telegram_message(telegram_message)
                        sent_lights_on = True
                        sent_lights_off = False

            except Exception as e_inner:
                log_message(f"⚠️ Error during monitoring: {e_inner}")
                log_message("🔄 Re-logging into Growatt...")
                inverter_sn = login_growatt()

            time.sleep(40)

    except Exception as e_outer:
        log_message(f"❌ Fatal error: {e_outer}")

# Function to send inverter status on Telegram
def send_inverter_data(update: Update, context: CallbackContext):
    message = f"""\
AC INPUT: {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
AC OUTPUT: {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Household load: {current_data.get('load_power', 'N/A')} W
Battery %: {current_data.get('battery_capacity', 'N/A')}%"""
    update.message.reply_text(message)

# Function to handle /start
def start(update: Update, context: CallbackContext):
    update.message.reply_text("✅ Welcome to the Growatt Monitor! Use /status to get inverter data.")

# Setup Telegram Bot
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("status", send_inverter_data))
updater.start_polling()

# Web interface
@app.route("/")
def home():
    return "✅ Growatt Monitor is Running!"

@app.route("/logs")
def get_logs():
    return render_template_string("""
    <html>
    <head>
        <title>Growatt Monitor - Data</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="refresh" content="40">
        <style>
            body { font-family: Arial, sans-serif; text-align: center; background: #f5f5f5; }
            h1 { font-size: 36px; margin-top: 20px; }
            table { margin: 0 auto; font-size: 30px; }
            td, th { padding: 10px 20px; }
            p { font-size: 20px; margin-top: 20px; }
        </style>
    </head>
    <body>
        <h1>Growatt Current Data</h1>
        <table border="1">
            <tr><th>AC Input Voltage</th><td>{{ current_data['ac_input_voltage'] }}</td></tr>
            <tr><th>AC Input Frequency</th><td>{{ current_data['ac_input_frequency'] }}</td></tr>
            <tr><th>AC Output Voltage</th><td>{{ current_data['ac_output_voltage'] }}</td></tr>
            <tr><th>AC Output Frequency</th><td>{{ current_data['ac_output_frequency'] }}</td></tr>
            <tr><th>Active Power (Load)</th><td>{{ current_data['load_power'] }}</td></tr>
            <tr><th>Battery Capacity</th><td>{{ current_data['battery_capacity'] }}</td></tr>
        </table>
        <p><b>Last Update:</b> {{ last_update_time }}</p>
    </body>
    </html>
    """, current_data=current_data, last_update_time=last_update_time)

@app.route("/console")
def get_console():
    return render_template_string("""
    <html>
    <head>
        <title>Growatt Monitor - Console</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="refresh" content="10">
        <style>
            body { font-family: monospace; background: #000; color: #0f0; padding: 10px; }
            pre { white-space: pre-wrap; word-wrap: break-word; }
        </style>
    </head>
    <body>
        <h1>Console Logs</h1>
        <pre>{{ logs }}</pre>
    </body>
    </html>
    """, logs="\n".join(logs))

# Start everything
if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)