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
TELEGRAM_TOKEN = "7653969082:AAH-HYF-jpuA8wplI4rbciv59s2ZD_xW7iE"
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
all_data = {}
last_update_time = "Never"
console_logs = []
updater = None  # Global reference

# Navigation
NAV_LINKS = """
<div style="font-size:20px; margin-bottom:20px;">
    <a href="/">Inicio</a> |
    <a href="/logs">/logs</a> |
    <a href="/chatlog">/chatlog</a> |
    <a href="/console">/console</a> |
    <a href="/details">/details</a>
</div>
"""

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

def login_and_fetch_data():
    log_message("🔄 Logging in to Growatt...")
    login_response = api.login(username, password)
    user_id = login_response["user"]["id"]
    plant_info = api.plant_list(user_id)
    plant_id = plant_info["data"][0]["plantId"]
    device_info = api.device_list(plant_id)
    inverter_info = api.inverter_list(plant_id)
    inverter_sn = inverter_info[0]["deviceSn"]
    storage_info = api.storage_detail(inverter_sn)

    all_data.clear()
    all_data.update({
        "login": login_response["user"],
        "plant": plant_info["data"][0],
        "device": device_info["data"][0],
        "inverter": inverter_info[0],
        "storage": storage_info
    })

    return inverter_sn, user_id, plant_id

def monitor_growatt():
    global last_update_time
    threshold = 80
    sent_lights_off = False
    sent_lights_on = False

    try:
        inverter_sn, user_id, plant_id = login_and_fetch_data()
        log_message("✅ Initialization successful!")

        while True:
            try:
                storage_info = api.storage_detail(inverter_sn)
                all_data["storage"] = storage_info

                ac_input_v = storage_info.get("vGrid", "N/A")
                ac_input_f = storage_info.get("freqGrid", "N/A")
                ac_output_v = storage_info.get("outPutVolt", "N/A")
                ac_output_f = storage_info.get("freqOutPut", "N/A")
                load_w = storage_info.get("activePower", "N/A")
                battery_pct = storage_info.get("capacity", "N/A")

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
                    if float(ac_input_v) < threshold and not sent_lights_off:
                        msg = f"""🔴🔴¡Se fue la luz en Acacías!🔴🔴

Nivel de batería      : {battery_pct} %
Voltaje de la red     : {ac_input_v} V / {ac_input_f} Hz
Voltaje del inversor: {ac_output_v} V / {ac_output_f} Hz
Consumo actual     : {load_w} W"""
                        send_telegram_message(msg)
                        send_telegram_message(msg)
                        sent_lights_off = True
                        sent_lights_on = False

                    elif float(ac_input_v) >= threshold and not sent_lights_on:
                        msg = f"""✅✅¡Llegó la luz en Acacías!✅✅

Nivel de batería      : {battery_pct} %
Voltaje de la red     : {ac_input_v} V / {ac_input_f} Hz
Voltaje del inversor: {ac_output_v} V / {ac_output_f} Hz
Consumo actual     : {load_w} W"""
                        send_telegram_message(msg)
                        send_telegram_message(msg)
                        sent_lights_on = True
                        sent_lights_off = False

            except Exception as e_inner:
                log_message(f"⚠️ Error during monitoring: {e_inner}")
                inverter_sn, _, _ = login_and_fetch_data()

            time.sleep(10)

    except Exception as e_outer:
        log_message(f"❌ Fatal error: {e_outer}")

@app.route("/")
def home():
    return NAV_LINKS + "✅ Growatt Monitor is Running!"

@app.route("/logs")
def get_logs():
    return NAV_LINKS + render_template_string("""
        <h1>Datos del Inversor</h1>
        <table border="1">
            <tr><th>AC Input Voltage</th><td>{{ d['ac_input_voltage'] }}</td></tr>
            <tr><th>AC Input Frequency</th><td>{{ d['ac_input_frequency'] }}</td></tr>
            <tr><th>AC Output Voltage</th><td>{{ d['ac_output_voltage'] }}</td></tr>
            <tr><th>AC Output Frequency</th><td>{{ d['ac_output_frequency'] }}</td></tr>
            <tr><th>Load Power</th><td>{{ d['load_power'] }}</td></tr>
            <tr><th>Battery Capacity</th><td>{{ d['battery_capacity'] }}</td></tr>
        </table>
        <p><b>Última actualización:</b> {{ last }}</p>
    """, d=current_data, last=last_update_time)

@app.route("/chatlog")
def chatlog_view():
    return NAV_LINKS + jsonify(sorted(list(chat_log)))

@app.route("/console")
def console_view():
    return NAV_LINKS + render_template_string("""
        <h2>Console Output (últimos 5 minutos)</h2>
        <pre>{{ logs }}</pre>
    """, logs="\n".join(m for _, m in console_logs))

@app.route("/details")
def details_view():
    html = NAV_LINKS
    static_info = all_data.get("device", {})
    html += "<h2>Información Estática</h2><ul>"
    for k in ["plantName", "plantId", "deviceSn", "deviceType", "firmwareVersion"]:
        if k in static_info:
            html += f"<li><b>{k}:</b> {static_info[k]}</li>"
    html += "</ul><hr><h2>Datos Detallados</h2><table style='font-size:14px;width:100%;'><tr><td><ul>"

    half = len(all_data["storage"]) // 2
    for i, (k, v) in enumerate(all_data["storage"].items()):
        if i == half:
            html += "</ul></td><td><ul>"
        html += f"<li><b>{k}:</b> {v}</li>"

    html += "</ul></td></tr></table>"
    return html

# Telegram Bot
def start(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    update.message.reply_text("¡Bienvenido al monitor Growatt! Usa /status para ver el estado del inversor.")

def send_status(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    msg = f"""⚡ Estado del Inversor ⚡

Voltaje Red       : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje Inversor: {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo          : {current_data.get('load_power', 'N/A')} W
Batería              : {current_data.get('battery_capacity', 'N/A')}%"""
    update.message.reply_text(msg)

def send_chatlog(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    ids = "\n".join(str(cid) for cid in chat_log)
    update.message.reply_text(f"IDs registrados:\n{ids}")

def stop_bot(update: Update, context: CallbackContext):
    update.message.reply_text("Bot detenido.")
    log_message("Bot detenido por comando /stop")
    threading.Thread(target=updater.stop).start()

# Init Telegram
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("status", send_status))
dp.add_handler(CommandHandler("chatlog", send_chatlog))
dp.add_handler(CommandHandler("stop", stop_bot))
updater.start_polling()

# Start Threads
if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)