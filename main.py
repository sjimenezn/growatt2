from flask import Flask, render_template_string, jsonify
import threading
import time
import requests
import datetime
from growattServer import GrowattApi
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters

# Credentials
username = "vospina"
password = "Vospina.2025"

# Telegram Config
TELEGRAM_TOKEN = "7653969082:AAGJ5_P23E6SbkJnTSHOjHhUGlKwcE_hao8"
CHAT_IDS = ["5715745951", "7862573365"]
chat_log = []

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

def log_message(message):
    print(message)
    logs.append(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}")
    if len(logs) > 2000:
        del logs[:1000]

def login_growatt():
    log_message("🔄 Attempting Growatt login...")
    login_response = api.login(username, password)
    plant_info = api.plant_list(login_response['user']['id'])
    plant_id = plant_info['data'][0]['plantId']
    inverter_info = api.inverter_list(plant_id)
    inverter_sn = inverter_info[0]['deviceSn']
    log_message(f"🌿 User ID: {login_response['user']['id']}")
    log_message(f"🌿 Plant ID: {plant_id}")
    return inverter_sn, login_response, plant_info

def monitor_growatt():
    global last_update_time
    ac_input_threshold = 90
    sent_lights_off = False
    sent_lights_on = False

    try:
        inverter_sn, _, _ = login_growatt()
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

                if ac_input_v != "N/A":
                    if float(ac_input_v) < ac_input_threshold and not sent_lights_off:
                        telegram_message = f"""⚠️ ¡Se fue la luz en Acacías! ⚠️

Nivel de batería: {battery_pct} %

Voltaje de la red: {ac_input_v} V / {ac_input_f} Hz
Voltaje Inversor: {ac_output_v} V / {ac_output_f} Hz

Consumo Actual: {load_w} W"""
                        send_telegram_message(telegram_message)
                        send_telegram_message(telegram_message)
                        sent_lights_off = True
                        sent_lights_on = False

                    elif float(ac_input_v) >= ac_input_threshold and not sent_lights_on:
                        telegram_message = f"""⚠️ ¡Llegó la luz en Acacías! ⚠️

Nivel de batería: {battery_pct} %

Voltaje de la red: {ac_input_v} V / {ac_input_f} Hz
Voltaje Inversor: {ac_output_v} V / {ac_output_f} Hz

Consumo Actual: {load_w} W"""
                        send_telegram_message(telegram_message)
                        send_telegram_message(telegram_message)
                        sent_lights_on = True
                        sent_lights_off = False

            except Exception as e_inner:
                log_message(f"⚠️ Error during monitoring: {e_inner}")
                log_message("🔄 Re-logging into Growatt...")
                inverter_sn, _, _ = login_growatt()

            time.sleep(40)

    except Exception as e_outer:
        log_message(f"❌ Fatal error: {e_outer}")

# Telegram Handlers
def send_inverter_data(update: Update, context: CallbackContext):
    message = f"""\
⚡ ENERGÍA ACTUAL ⚡

Entrada: {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Salida: {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo: {current_data.get('load_power', 'N/A')} W
Batería: {current_data.get('battery_capacity', 'N/A')}%"""
    update.message.reply_text(message)

def alldata_command(update: Update, context: CallbackContext):
    _, login_data, plant_data = login_growatt()
    update.message.reply_text(f"Plant Name: {plant_data['data'][0]['plantName']}\nUser ID: {login_data['user']['id']}\nRaw Data:\n{plant_data}")

def log_chat_id(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if str(user_id) not in CHAT_IDS:
        CHAT_IDS.append(str(user_id))
        log_message(f"New Telegram user logged: {user_id}")
    chat_log.append(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {user_id} - {update.message.text}")

def chatlog_command(update: Update, context: CallbackContext):
    log_text = "\n".join(chat_log[-50:]) or "No activity yet."
    update.message.reply_text(f"Últimos usuarios:\n{log_text}")

# Setup Telegram Bot
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("Bienvenido al Monitor Growatt.")))
dp.add_handler(CommandHandler("status", send_inverter_data))
dp.add_handler(CommandHandler("alldata", alldata_command))
dp.add_handler(CommandHandler("chatlog", chatlog_command))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, log_chat_id))
updater.start_polling()

# Flask Routes
@app.route("/")
def home():
    return "✅ Growatt Monitor is Running!"

@app.route("/logs")
def get_logs():
    return render_template_string("<pre>{{ logs }}</pre>", logs="\n".join(logs[-200:]))

@app.route("/chatlog")
def get_chatlog():
    return render_template_string("<pre>{{ chat_log }}</pre>", chat_log="\n".join(chat_log[-200:]))

# Start everything
if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)