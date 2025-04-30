from flask import Flask, render_template_string, jsonify
import threading
import time
import requests
import datetime
from growattServer import GrowattApi
# from telegram import Update
# from telegram.ext import Updater, CommandHandler, CallbackContext

# Credentials
username = "vospina"
password = "Vospina.2025"

# Telegram Config (commented out for testing)
# TELEGRAM_TOKEN = "7653969082:AAH-HYF-jpuA8wplI4rbciv59s2ZD_xW7iE"
# CHAT_IDS = ["7650630450", "7862573365", "5715745951"]
# chat_log = set()

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
all_storage_data = {}
# updater = None  # Global reference

def log_message(message):
    timestamped = f"{datetime.datetime.now().strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now = time.time()
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 300]

# def send_telegram_message(message):
#     for chat_id in CHAT_IDS:
#         try:
#             url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
#             payload = {"chat_id": chat_id, "text": message}
#             requests.post(url, data=payload, timeout=10)
#         except Exception as e:
#             log_message(f"❌ Failed to send message to {chat_id}: {e}")

def login_growatt():
    log_message("🔄 Attempting Growatt login...")
    login_response = api.login(username, password)
    user_id = login_response['user']['id']
    plant_info = api.plant_list(user_id)
    plant_id = plant_info['data'][0]['plantId']
    inverter_info = api.inverter_list(plant_id)
    inverter_sn = inverter_info[0]['deviceSn']
    log_message(f"🌿 User ID: {user_id}")
    log_message(f"🌿 Plant ID: {plant_id}")
    log_message(f"🔌 Inverter SN: {inverter_sn}")
    return inverter_sn

def monitor_growatt():
    global last_update_time, all_storage_data
    threshold = 80
    sent_lights_off = False
    sent_lights_on = False

    try:
        inverter_sn = login_growatt()
        log_message("✅ Growatt login and initialization successful!")

        while True:
            try:
                data = api.storage_detail(inverter_sn)
                all_storage_data = data.get("data", {}) or {}

                ac_input_v = all_storage_data.get("vGrid", "N/A")
                ac_input_f = all_storage_data.get("freqGrid", "N/A")
                ac_output_v = all_storage_data.get("outPutVolt", "N/A")
                ac_output_f = all_storage_data.get("freqOutPut", "N/A")
                load_w = all_storage_data.get("activePower", "N/A")
                battery_pct = all_storage_data.get("capacity", "N/A")

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

                # Alert logic (commented out for now)
                # if ac_input_v != "N/A":
                #     if float(ac_input_v) < threshold and not sent_lights_off:
                #         msg = f"..."
                #         send_telegram_message(msg)
                #         send_telegram_message(msg)
                #         sent_lights_off = True
                #         sent_lights_on = False
                #     elif float(ac_input_v) >= threshold and not sent_lights_on:
                #         msg = f"..."
                #         send_telegram_message(msg)
                #         send_telegram_message(msg)
                #         sent_lights_on = True
                #         sent_lights_off = False

            except Exception as e_inner:
                log_message(f"⚠️ Error during monitoring: {e_inner}")
                inverter_sn = login_growatt()

            time.sleep(40)

    except Exception as e_outer:
        log_message(f"❌ Fatal error: {e_outer}")

# Telegram Handlers (commented out for testing)
# def start(update: Update, context: CallbackContext):
#     chat_log.add(update.effective_chat.id)
#     update.message.reply_text("¡Bienvenido al monitor Growatt! Usa /status para ver el estado del inversor.")

# def send_status(update: Update, context: CallbackContext):
#     chat_log.add(update.effective_chat.id)
#     msg = f"..."
#     update.message.reply_text(msg)

# def send_chatlog(update: Update, context: CallbackContext):
#     chat_log.add(update.effective_chat.id)
#     ids = "\n".join(str(cid) for cid in chat_log)
#     update.message.reply_text(f"IDs registrados:\n{ids}")

# def stop_bot(update: Update, context: CallbackContext):
#     update.message.reply_text("Bot detenido.")
#     log_message("Bot detenido por comando /stop")
#     threading.Thread(target=updater.stop).start()

# updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
# dp = updater.dispatcher
# dp.add_handler(CommandHandler("start", start))
# dp.add_handler(CommandHandler("status", send_status))
# dp.add_handler(CommandHandler("chatlog", send_chatlog))
# dp.add_handler(CommandHandler("stop", stop_bot))
# updater.start_polling()

# Flask Routes
@app.route("/")
def home():
    return "✅ Growatt Monitor is Running!"

@app.route("/logs")
def get_logs():
    return render_template_string("""
        <html><head><title>Growatt Monitor - Logs</title><meta http-equiv="refresh" content="40"></head>
        <body>
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
        </body></html>
    """, d=current_data, last=last_update_time)

@app.route("/details")
def all_details():
    return render_template_string("""
        <html><head><title>All Storage Data</title><meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: sans-serif; font-size: 18px; padding: 20px; }
            table { width: 100%; border-collapse: collapse; }
            td, th { border: 1px solid #ccc; padding: 8px; }
        </style>
        </head>
        <body>
            <h2>Growatt Full Storage Details</h2>
            <table>
                {% for key, val in data.items() %}
                <tr><th>{{ key }}</th><td>{{ val }}</td></tr>
                {% endfor %}
            </table>
            <p><b>Última actualización:</b> {{ last }}</p>
        </body></html>
    """, data=all_storage_data, last=last_update_time)

@app.route("/console")
def console_view():
    return render_template_string("""
        <html><head><title>Console Logs</title><meta http-equiv="refresh" content="10"></head>
        <body>
            <h2>Console Output (últimos 5 minutos)</h2>
            <pre>{{ logs }}</pre>
        </body></html>
    """, logs="\n".join(m for _, m in console_logs))

if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)