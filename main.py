
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
TELEGRAM_TOKEN = "7653969082:AAExMmdyKRo4WOHIhm8NPNWbDyCy6Cl8dD8"
CHAT_IDS = ["5715745951"]  # Only sends messages to 'sergiojim' chat ID
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
updater = None  # Global reference

def log_message(message):
    timestamped = f"{datetime.datetime.now().strftime('%H:%M:%S')} - {message}"
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

def login_growatt():
    log_message("🔄 Attempting Growatt login...")
    login_response = api.login(username, password)
    plant_info = api.plant_list(login_response['user']['id'])
    plant_id = plant_info['data'][0]['plantId']
    inverter_info = api.inverter_list(plant_id)
    inverter_sn = inverter_info[0]['deviceSn']
    datalogger_info = api.storage_detail(inverter_sn)
    datalog_sn = datalogger_info.get("dataloggerSn", "N/A")
    
    log_message(f"🌿 User ID: {login_response['user']['id']}")
    log_message(f"🌿 Plant ID: {plant_id}")
    log_message(f"🌿 Inverter SN: {inverter_sn}")
    log_message(f"🌿 Datalogger SN: {datalog_sn}")
    
    return login_response['user']['id'], plant_id, inverter_sn, datalog_sn

def monitor_growatt():
    global last_update_time
    threshold = 80
    sent_lights_off = False
    sent_lights_on = False

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

                last_update_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_message(f"Updated current_data: {current_data}")

                if ac_input_v != "N/A":
                    if float(ac_input_v) < threshold and not sent_lights_off:
                        time.sleep(110)
                        data = api.storage_detail(inverter_sn)
                        ac_input_v = data.get("vGrid", "N/A")
                        if float(ac_input_v) < threshold:
                            msg = f"""🔴🔴¡Se fue la luz en Acacías!🔴🔴

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
    msg = f"""⚡ Estado del Inversor /stop⚡

Voltaje Red       : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje Inversor: {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo          : {current_data.get('load_power', 'N/A')} W
Batería              : {current_data.get('battery_capacity', 'N/A')}%"""
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
    threading.Thread(target=updater.stop).start()

updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("status", send_status))
dp.add_handler(CommandHandler("chatlog", send_chatlog))
dp.add_handler(CommandHandler("stop", stop_bot))

# Stop the existing Telegram bot instance before starting
if updater.running:
    updater.stop()
updater.start_polling()

# Flask Routes
@app.route("/")
def home():
    return render_template_string("""
        <html><head><title>Home - Growatt Monitor</title></head>
        <body>
            <h1>✅ Growatt Monitor is Running!</h1>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a></li>
                    <li><a href="/chatlog">Chatlog</a></li>
                    <li><a href="/console">Console</a></li>
                    <li><a href="/details">Details</a></li>
                </ul>
            </nav>
        </body></html>
    """)

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
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a></li>
                    <li><a href="/chatlog">Chatlog</a></li>
                    <li><a href="/console">Console</a></li>
                    <li><a href="/details">Details</a></li>
                </ul>
            </nav>
        </body></html>
    """, d=current_data, last=last_update_time)

@app.route("/chatlog")
def chatlog_view():
    return render_template_string("""
        <html><head><title>Growatt Monitor - Chatlog</title></head>
        <body>
            <h1>Chatlog</h1>
            <pre>{{ chat_log }}</pre>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a></li>
                    <li><a href="/chatlog">Chatlog</a></li>
                    <li><a href="/console">Console</a></li>
                    <li><a href="/details">Details</a></li>
                </ul>
            </nav>
        </body></html>
    """, chat_log="\n".join(str(cid) for cid in sorted(list(chat_log))))

@app.route("/console")
def console_view():
    return render_template_string("""
        <html><head><title>Console Logs</title><meta http-equiv="refresh" content="10"></head>
        <body>
            <h2>Console Output (últimos 5 minutos)</h2>
            <pre>{{ logs }}</pre>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a></li>
                    <li><a href="/chatlog">Chatlog</a></li>
                    <li><a href="/console">Console</a></li>
                    <li><a href="/details">Details</a></li>
                </ul>
            </nav>
        </body></html>
    """, logs="\n".join(m for _, m in console_logs))

@app.route("/details")
def details_view():
    return render_template_string("""
        <html><head><title>Growatt Details</title><meta http-equiv="refresh" content="40"></head>
        <body>
            <h1>Detalles del Inversor</h1>
            <h2>Información constante</h2>
            <p>Plant ID: {{ plant_id }}</p>
            <p>User ID: {{ user_id }}</p>
            <p>Inverter SN: {{ inverter_sn }}</p>
            <p>Datalogger SN: {{ datalog_sn }}</p>
            <h2>Datos en tiempo real</h2>
            <table border="1">
                <tr><th>AC Input Voltage</th><td>{{ d['ac_input_voltage'] }}</td></tr>
                <tr><th>AC Input Frequency</th><td>{{ d['ac_input_frequency'] }}</td></tr>
                <tr><th>AC Output Voltage</th><td>{{ d['ac_output_voltage'] }}</td></tr>
                <tr><th>AC Output Frequency</th><td>{{ d['ac_output_frequency'] }}</td></tr>
                <tr><th>Load Power</th><td>{{ d['load_power'] }}</td></tr>
                <tr><th>Battery Capacity</th><td>{{ d['battery_capacity'] }}</td></tr>
            </table>
            <p><b>Última actualización:</b> {{ last }}</p>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a></li>
                    <li><a href="/chatlog">Chatlog</a></li>
                    <li><a href="/console">Console</a></li>
                    <li><a href="/details">Details</a></li>
                </ul>
            </nav>
        </body></html>
    """, d=current_data, last=last_update_time,
       plant_id=current_data.get("plant_id", "N/A"),
       user_id=current_data.get("user_id", "N/A"),
       inverter_sn=current_data.get("inverter_sn", "N/A"),
       datalog_sn=current_data.get("datalog_sn", "N/A"))


if __name__ == '__main__':
    threading.Thread(target=monitor_growatt).start()
    app.run(host='0.0.0.0', port=8000)
