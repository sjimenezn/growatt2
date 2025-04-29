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
TELEGRAM_TOKEN = "7653969082:AAEgaA1W8sjOnMv4vrE5DX7rqyWSsDMcetg"
CHAT_IDS = ["5715745951", "7862573365"]
interacted_chat_ids = set()

# Setup Flask app
app = Flask(__name__)

# Setup Growatt API
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})

current_data = {}
last_update_time = "Never"
console_logs = []

def log_message(message):
    timestamp = datetime.datetime.now()
    console_logs.append((timestamp, message))
    print(message)
    # Purge logs older than 5 minutes
    five_min_ago = datetime.datetime.now() - datetime.timedelta(minutes=5)
    while console_logs and console_logs[0][0] < five_min_ago:
        console_logs.pop(0)

def send_telegram_message(message):
    for chat_id in CHAT_IDS:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        try:
            requests.post(url, data=payload, timeout=10)
        except Exception as e:
            log_message(f"❌ Failed to send Telegram message: {e}")

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

def monitor_growatt():
    global last_update_time
    ac_input_threshold = 80
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

                log_message(f"Updated Data: {current_data}")

                if ac_input_v != "N/A":
                    if float(ac_input_v) < ac_input_threshold and not sent_lights_off:
                        msg = f"""⚠️ ¡Se fue la luz en Acacías! ⚠️

Nivel de batería: {battery_pct} %

Voltaje de la red: {ac_input_v} V / {ac_input_f} Hz
Voltaje Inversor : {ac_output_v} V / {ac_output_f} Hz

Consumo Actual: {load_w} W"""
                        send_telegram_message(msg)
                        send_telegram_message(msg)
                        sent_lights_off = True
                        sent_lights_on = False

                    elif float(ac_input_v) >= ac_input_threshold and not sent_lights_on:
                        msg = f"""⚠️ ¡Llegó la luz en Acacías! ⚠️

Nivel de batería: {battery_pct} %

Voltaje de la red: {ac_input_v} V / {ac_input_f} Hz
Voltaje Inversor : {ac_output_v} V / {ac_output_f} Hz

Consumo Actual: {load_w} W"""
                        send_telegram_message(msg)
                        send_telegram_message(msg)
                        sent_lights_on = True
                        sent_lights_off = False

            except Exception as e_inner:
                log_message(f"⚠️ Error during monitoring: {e_inner}")
                log_message("🔄 Re-logging into Growatt...")
                inverter_sn = login_growatt()

            time.sleep(40)

    except Exception as e_outer:
        log_message(f"❌ Fatal error: {e_outer}")

# Telegram handlers
def start(update: Update, context: CallbackContext):
    interacted_chat_ids.add(update.effective_chat.id)
    update.message.reply_text("Bienvenido al monitor Growatt. Usa /status para obtener el estado actual.")

def send_inverter_data(update: Update, context: CallbackContext):
    interacted_chat_ids.add(update.effective_chat.id)
    msg = f"""⚙️ *Estado actual del inversor:*

Voltaje de entrada: {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje de salida: {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo actual: {current_data.get('load_power', 'N/A')} W
Batería: {current_data.get('battery_capacity', 'N/A')} %"""
    update.message.reply_text(msg, parse_mode="Markdown")

def show_chat_ids(update: Update, context: CallbackContext):
    ids_list = "\n".join(str(cid) for cid in interacted_chat_ids)
    update.message.reply_text(f"Chat IDs interactuando con el bot:\n{ids_list}")

# Set up Telegram bot
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("status", send_inverter_data))
dp.add_handler(CommandHandler("chatlog", show_chat_ids))
updater.start_polling()

@app.route("/")
def home():
    return "✅ Growatt Monitor is Running!"

@app.route("/logs")
def get_logs():
    return render_template_string("""
        <html><head><meta http-equiv="refresh" content="40"></head><body>
        <h1>Growatt Data</h1>
        <table border="1">
        <tr><th>AC Input Voltage</th><td>{{ data['ac_input_voltage'] }}</td></tr>
        <tr><th>AC Output Voltage</th><td>{{ data['ac_output_voltage'] }}</td></tr>
        <tr><th>Active Power</th><td>{{ data['load_power'] }}</td></tr>
        <tr><th>Battery Capacity</th><td>{{ data['battery_capacity'] }}</td></tr>
        </table><p><b>Last update:</b> {{ last_update }}</p></body></html>
    """, data=current_data, last_update=last_update_time)

@app.route("/chatlog")
def chatlog():
    return jsonify(sorted(interacted_chat_ids))

@app.route("/console")
def console():
    return render_template_string("""
    <html><head><meta http-equiv="refresh" content="10"><title>Console</title></head><body>
    <h1>Últimos mensajes de consola (últimos 5 minutos)</h1><pre>
    {% for ts, msg in logs %}[{{ ts.strftime('%H:%M:%S') }}] {{ msg }}
    {% endfor %}</pre></body></html>
    """, logs=console_logs)

if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)