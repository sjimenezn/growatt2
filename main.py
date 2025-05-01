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
TELEGRAM_TOKEN = "7653969082:AAEUaLVA9mHCvd5oQKPRUigoh0dkIxRbyt4"
CHAT_IDS = ["7650630450", "7862573365", "5715745951"]
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
all_raw_data = {}
last_update_time = "Never"
console_logs = []
updater = None
static_info = {}

def log_message(message):
    timestamped = f"{datetime.datetime.now().strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now = time.time()
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 300]

def send_telegram_message(message):
    for chat_id in CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": chat_id, "text": message}
            requests.post(url, data=payload, timeout=10)
        except Exception as e:
            log_message(f"❌ Failed to send message to {chat_id}: {e}")

def login_growatt():
    log_message("🔄 Attempting Growatt login...")
    login_response = api.login(username, password)
    user_id = login_response['user']['id']
    plant_info = api.plant_list(user_id)
    plant_id = plant_info['data'][0]['plantId']
    device_info = api.device_list(plant_id)
    inverter_info = api.inverter_list(plant_id)
    inverter_sn = inverter_info[0]['deviceSn']
    datalog_sn = device_info[0]['datalogSn']
    static_info.update({
        "user_id": user_id,
        "plant_id": plant_id,
        "inverter_sn": inverter_sn,
        "datalogger_sn": datalog_sn
    })
    return inverter_sn

def fetch_all_data(inverter_sn):
    login_response = api.login(username, password)
    plant_info = api.plant_list(login_response['user']['id'])
    device_info = api.device_list(plant_info['data'][0]['plantId'])
    inverter_info = api.inverter_list(plant_info['data'][0]['plantId'])
    storage_info = api.storage_detail(inverter_sn)

    all_raw_data.update({
        "login": login_response,
        "plant_list": plant_info,
        "device_list": device_info,
        "inverter_list": inverter_info,
        "storage_detail": storage_info
    })

def monitor_growatt():
    global last_update_time
    threshold = 135
    sent_lights_off = False
    sent_lights_on = False

    try:
        inverter_sn = login_growatt()
        log_message("✅ Growatt login and initialization successful!")

        while True:
            try:
                data = api.storage_detail(inverter_sn)
                fetch_all_data(inverter_sn)

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
                    voltage = float(ac_input_v)
                    if voltage < threshold and not sent_lights_off:
                        msg = f"""🔴🔴 Power Outage in Acacías! 🔴🔴

Battery Level   : {battery_pct} %
Grid Voltage    : {ac_input_v} V / {ac_input_f} Hz
Inverter Voltage: {ac_output_v} V / {ac_output_f} Hz
Current Load    : {load_w} W"""
                        send_telegram_message(msg)
                        send_telegram_message(msg)
                        sent_lights_off = True
                        sent_lights_on = False

                    elif voltage >= threshold and not sent_lights_on:
                        msg = f"""✅✅ Power Restored in Acacías! ✅✅

Battery Level   : {battery_pct} %
Grid Voltage    : {ac_input_v} V / {ac_input_f} Hz
Inverter Voltage: {ac_output_v} V / {ac_output_f} Hz
Current Load    : {load_w} W"""
                        send_telegram_message(msg)
                        send_telegram_message(msg)
                        sent_lights_on = True
                        sent_lights_off = False

            except Exception as e_inner:
                log_message(f"⚠️ Monitoring error: {e_inner}")
                inverter_sn = login_growatt()

            time.sleep(10)

    except Exception as e_outer:
        log_message(f"❌ Fatal error: {e_outer}")

def nav_links():
    return """
    <div style='font-size:20px; margin-bottom:20px;'>
        <a href='/'>Home</a> |
        <a href='/logs'>Logs</a> |
        <a href='/chatlog'>Chat Log</a> |
        <a href='/console'>Console</a> |
        <a href='/details'>Details</a>
    </div>
    """

@app.route("/")
def home():
    return nav_links() + "✅ Growatt Monitor is Running!"

@app.route("/logs")
def get_logs():
    return nav_links() + render_template_string("""
        <h2>Inverter Data</h2>
        <table border="1">
            {% for key, val in data.items() %}
            <tr><th>{{ key }}</th><td>{{ val }}</td></tr>
            {% endfor %}
        </table>
        <p><b>Last Update:</b> {{ last }}</p>
    """, data=current_data, last=last_update_time)

@app.route("/chatlog")
def chatlog_view():
    return jsonify(sorted(list(chat_log)))

@app.route("/console")
def console_view():
    return nav_links() + render_template_string("""
        <h2>Console Output (last 5 minutes)</h2>
        <pre>{{ logs }}</pre>
    """, logs="\n".join(m for _, m in console_logs))

@app.route("/details")
def details():
    storage = all_raw_data.get("storage_detail", {})
    inverter_list = all_raw_data.get("inverter_list", [{}])[0]
    datalog_sn = static_info.get("datalogger_sn", "N/A")

    return nav_links() + render_template_string("""
        <h2>System Details</h2>
        <p><b>Datalogger SN:</b> {{ datalog_sn }}</p>
        <div style="display:flex; flex-wrap:wrap;">
            <div style="width:50%;">
                <table border="1">
                    {% for key, val in left.items() %}
                    <tr><th>{{ key }}</th><td>{{ val }}</td></tr>
                    {% endfor %}
                </table>
            </div>
            <div style="width:50%;">
                <table border="1">
                    {% for key, val in right.items() %}
                    <tr><th>{{ key }}</th><td>{{ val }}</td></tr>
                    {% endfor %}
                </table>
            </div>
        </div>
        <p><b>Last Update:</b> {{ last }}</p>
    """, datalog_sn=datalog_sn, left=dict(list(storage.items())[:len(storage)//2]), right=dict(list(storage.items())[len(storage)//2:]), last=last_update_time)

# Telegram Bot Handlers
def start(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    update.message.reply_text("Welcome to the Growatt Monitor! Use /status to check the inverter status.")

def send_status(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    msg = f"""⚡ Inverter Status ⚡

Grid Voltage    : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Inverter Output : {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Current Load    : {current_data.get('load_power', 'N/A')} W
Battery Level   : {current_data.get('battery_capacity', 'N/A')}%"""
    update.message.reply_text(msg)

def send_chatlog(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    ids = "\n".join(str(cid) for cid in chat_log)
    update.message.reply_text(f"Registered IDs:\n{ids}")

def stop_bot(update: Update, context: CallbackContext):
    update.message.reply_text("Bot stopped.")
    log_message("Bot stopped with /stop command")
    threading.Thread(target=updater.stop).start()

# Start Telegram Bot
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("status", send_status))
dp.add_handler(CommandHandler("chatlog", send_chatlog))
dp.add_handler(CommandHandler("stop", stop_bot))
updater.start_polling()

# Launch Monitor
if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)