from flask import Flask, render_template_string, jsonify
import threading
import time
import requests
import datetime
from growattServer import GrowattApi
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# Credenciales
username = "vospina"
password = "Vospina.2025"

# Configuración de Telegram
TELEGRAM_TOKEN = "7653969082:AAH-HYF-jpuA8wplI4rbciv59s2ZD_xW7iE"
CHAT_IDS = ["7650630450", "7862573365", "5715745951"]
chat_log = set()

# App Flask
app = Flask(__name__)

# API Growatt
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})

# Datos compartidos
current_data = {}
last_update_time = "Nunca"
console_logs = []
all_data_snapshot = {}
updater = None  # Referencia global

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
            log_message(f"❌ Error enviando a {chat_id}: {e}")

def login_growatt():
    log_message("🔄 Iniciando sesión en Growatt...")
    login_response = api.login(username, password)
    user_id = login_response['user']['id']
    plant_info = api.plant_list(user_id)
    plant_id = plant_info['data'][0]['plantId']
    inverter_info = api.inverter_list(plant_id)
    inverter_sn = inverter_info[0]['deviceSn']
    log_message(f"🌿 Usuario ID: {user_id}")
    log_message(f"🌿 Planta ID: {plant_id}")
    return user_id, plant_id, inverter_sn

def monitor_growatt():
    global last_update_time, all_data_snapshot
    threshold = 80
    sent_lights_off = False
    sent_lights_on = False

    try:
        user_id, plant_id, inverter_sn = login_growatt()
        log_message("✅ Sesión Growatt exitosa!")

        while True:
            try:
                data = api.storage_detail(inverter_sn)

                current_data.update({
                    "ac_input_voltage": data.get("vGrid", "N/A"),
                    "ac_input_frequency": data.get("freqGrid", "N/A"),
                    "ac_output_voltage": data.get("outPutVolt", "N/A"),
                    "ac_output_frequency": data.get("freqOutPut", "N/A"),
                    "load_power": data.get("activePower", "N/A"),
                    "battery_capacity": data.get("capacity", "N/A")
                })

                all_data_snapshot = {
                    "user_id": user_id,
                    "plant_id": plant_id,
                    "inverter_sn": inverter_sn,
                    **data
                }

                last_update_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_message(f"Datos actualizados: {current_data}")

                if current_data["ac_input_voltage"] != "N/A":
                    val = float(current_data["ac_input_voltage"])
                    if val < threshold and not sent_lights_off:
                        msg = f"""🔴🔴¡Se fue la luz en Acacías!🔴🔴

Nivel de batería      : {current_data['battery_capacity']} %
Voltaje de la red     : {current_data['ac_input_voltage']} V / {current_data['ac_input_frequency']} Hz
Voltaje del inversor  : {current_data['ac_output_voltage']} V / {current_data['ac_output_frequency']} Hz
Consumo actual        : {current_data['load_power']} W"""
                        send_telegram_message(msg)
                        send_telegram_message(msg)
                        sent_lights_off = True
                        sent_lights_on = False

                    elif val >= threshold and not sent_lights_on:
                        msg = f"""✅✅¡Llegó la luz en Acacías!✅✅

Nivel de batería      : {current_data['battery_capacity']} %
Voltaje de la red     : {current_data['ac_input_voltage']} V / {current_data['ac_input_frequency']} Hz
Voltaje del inversor  : {current_data['ac_output_voltage']} V / {current_data['ac_output_frequency']} Hz
Consumo actual        : {current_data['load_power']} W"""
                        send_telegram_message(msg)
                        send_telegram_message(msg)
                        sent_lights_on = True
                        sent_lights_off = False

            except Exception as e_inner:
                log_message(f"⚠️ Error monitoreando: {e_inner}")
                user_id, plant_id, inverter_sn = login_growatt()

            time.sleep(10)

    except Exception as e_outer:
        log_message(f"❌ Error fatal: {e_outer}")

# Telegram
def start(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    update.message.reply_text("¡Bienvenido al monitor Growatt! Usa /status para ver el estado del inversor.")

def send_status(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    msg = f"""⚡ Estado del Inversor ⚡

Voltaje Red       : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje Inversor  : {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo           : {current_data.get('load_power', 'N/A')} W
Batería           : {current_data.get('battery_capacity', 'N/A')}%"""
    update.message.reply_text(msg)

def send_chatlog(update: Update, context: CallbackContext):
    chat_log.add(update.effective_chat.id)
    ids = "\n".join(str(cid) for cid in chat_log)
    update.message.reply_text(f"IDs registrados:\n{ids}")

def stop_bot(update: Update, context: CallbackContext):
    update.message.reply_text("Bot detenido.")
    log_message("Bot detenido por comando /stop")
    threading.Thread(target=updater.stop).start()

# Configurar comandos Telegram
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("status", send_status))
dp.add_handler(CommandHandler("chatlog", send_chatlog))
dp.add_handler(CommandHandler("stop", stop_bot))
updater.start_polling()

# Rutas Flask
@app.route("/")
def home():
    return "✅ Growatt Monitor ejecutándose!"

@app.route("/logs")
def get_logs():
    return render_template_string("""
        <html><head><title>Growatt Monitor - Logs</title><meta http-equiv="refresh" content="40"></head>
        <body>
            <h1>Datos del Inversor</h1>
            <table border="1">
                <tr><th>Voltaje Entrada AC</th><td>{{ d['ac_input_voltage'] }}</td></tr>
                <tr><th>Frecuencia Entrada AC</th><td>{{ d['ac_input_frequency'] }}</td></tr>
                <tr><th>Voltaje Salida AC</th><td>{{ d['ac_output_voltage'] }}</td></tr>
                <tr><th>Frecuencia Salida AC</th><td>{{ d['ac_output_frequency'] }}</td></tr>
                <tr><th>Potencia Carga</th><td>{{ d['load_power'] }}</td></tr>
                <tr><th>Batería (%)</th><td>{{ d['battery_capacity'] }}</td></tr>
            </table>
            <p><b>Última actualización:</b> {{ last }}</p>
        </body></html>
    """, d=current_data, last=last_update_time)

@app.route("/console")
def console_view():
    return render_template_string("""
        <html><head><title>Logs Consola</title><meta http-equiv="refresh" content="10"></head>
        <body><h2>Últimos Logs (5 min)</h2><pre>{{ logs }}</pre></body></html>
    """, logs="\n".join(m for _, m in console_logs))

@app.route("/chatlog")
def chatlog_view():
    return jsonify(sorted(list(chat_log)))

@app.route("/details")
def details():
    return render_template_string("""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Growatt - Detalles Completos</title>
        <meta http-equiv="refresh" content="10">
        <style>
            body { font-family: Arial, sans-serif; padding: 20px; font-size: 18px; }
            table { border-collapse: collapse; width: 100%; margin-top: 10px; }
            th, td { border: 1px solid #ddd; padding: 10px; font-size: 18px; }
            th { background-color: #f2f2f2; text-align: left; }
            h2 { font-size: 24px; }
        </style>
    </head>
    <body>
        <h2>Detalles Completos - Growatt</h2>
        <p><b>Última actualización:</b> {{ last }}</p>
        <table>
            <tr><th>ID Usuario</th><td>{{ data.get("user_id", "N/A") }}</td></tr>
            <tr><th>ID Planta</th><td>{{ data.get("plant_id", "N/A") }}</td></tr>
            <tr><th>Inversor SN</th><td>{{ data.get("inverter_sn", "N/A") }}</td></tr>
        </table>
        <h2>Datos Técnicos</h2>
        <table>
            {% for k, v in data.items() if k not in ['user_id', 'plant_id', 'inverter_sn'] %}
            <tr><th>{{ k }}</th><td>{{ v }}</td></tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """, data=all_data_snapshot, last=last_update_time)

# Lanzar app
if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)