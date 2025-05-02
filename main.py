from flask import Flask, render_template_string, jsonify
import threading
import time
import requests
import datetime
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

# Shared Data
current_data = {}
last_update_time = "Never"
console_logs = []

def log_message(message):
    timestamped = f"{datetime.datetime.now().strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now = time.time()
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 300]

# Monitor Growatt (simulated for now)
def monitor_growatt():
    global last_update_time
    try:
        while True:
            # Mock data for testing
            current_data.update({
                "ac_input_voltage": "230",
                "ac_input_frequency": "50",
                "ac_output_voltage": "220",
                "ac_output_frequency": "49.5",
                "load_power": "500",
                "battery_capacity": "85"
            })
            last_update_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            time.sleep(10)
    except Exception as e:
        log_message(f"Error in monitor_growatt: {e}")

# Telegram Handlers
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Bot is working!")

def status(update: Update, context: CallbackContext):
    update.message.reply_text(f"Current Data: {current_data}")

updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("status", status))
updater.start_polling()

# Navigation links
NAVIGATION_LINKS = """
<ul>
    <li><a href="/">Home</a></li>
    <li><a href="/logs">Logs</a></li>
    <li><a href="/chatlog">Chat Log</a></li>
    <li><a href="/console">Console Logs</a></li>
    <li><a href="/details">Details</a></li>
</ul>
"""

@app.route("/")
def home():
    return render_template_string(f"""
        <html>
        <head><title>Growatt Monitor - Home</title></head>
        <body>
            <h1>Welcome to Growatt Monitor!</h1>
            {NAVIGATION_LINKS}
        </body>
        </html>
    """)

@app.route("/logs")
def get_logs():
    return render_template_string("""
        <html>
        <head><title>Growatt Monitor - Logs</title><meta http-equiv="refresh" content="40"></head>
        <body>
            <h1>Logs</h1>
            {{ navigation_links|safe }}
            <table border="1">
                <tr><th>AC Input Voltage</th><td>{{ d['ac_input_voltage'] }}</td></tr>
                <tr><th>AC Input Frequency</th><td>{{ d['ac_input_frequency'] }}</td></tr>
                <tr><th>AC Output Voltage</th><td>{{ d['ac_output_voltage'] }}</td></tr>
                <tr><th>AC Output Frequency</th><td>{{ d['ac_output_frequency'] }}</td></tr>
                <tr><th>Load Power</th><td>{{ d['load_power'] }}</td></tr>
                <tr><th>Battery Capacity</th><td>{{ d['battery_capacity'] }}</td></tr>
            </table>
            <p><b>Last Update:</b> {{ last }}</p>
        </body>
        </html>
    """, d=current_data, last=last_update_time, navigation_links=NAVIGATION_LINKS)

@app.route("/chatlog")
def chatlog_view():
    return render_template_string("""
        <html>
        <head><title>Growatt Monitor - Chat Logs</title></head>
        <body>
            <h1>Chat Logs</h1>
            {{ navigation_links|safe }}
            <pre>{{ logs }}</pre>
        </body>
        </html>
    """, logs="\n".join(map(str, chat_log)), navigation_links=NAVIGATION_LINKS)

@app.route("/console")
def console_view():
    return render_template_string("""
        <html>
        <head><title>Growatt Monitor - Console Logs</title><meta http-equiv="refresh" content="10"></head>
        <body>
            <h1>Console Logs</h1>
            {{ navigation_links|safe }}
            <pre>{{ logs }}</pre>
        </body>
        </html>
    """, logs="\n".join(m for _, m in console_logs), navigation_links=NAVIGATION_LINKS)

@app.route("/details")
def details_view():
    return render_template_string("""
        <html>
        <head><title>Growatt Monitor - Details</title><meta http-equiv="refresh" content="40"></head>
        <body>
            <h1>Details</h1>
            {{ navigation_links|safe }}
            <h2>Constant Details</h2>
            <p>Plant ID: {{ plant_id }}</p>
            <p>User ID: {{ user_id }}</p>
            <p>Inverter SN: {{ inverter_sn }}</p>
            <p>Datalogger SN: {{ datalogger_sn }}</p>
            <h2>Real-Time Details</h2>
            <table border="1">
                <tr><th>AC Input Voltage</th><td>{{ d['ac_input_voltage'] }}</td></tr>
                <tr><th>AC Input Frequency</th><td>{{ d['ac_input_frequency'] }}</td></tr>
                <tr><th>AC Output Voltage</th><td>{{ d['ac_output_voltage'] }}</td></tr>
                <tr><th>AC Output Frequency</th><td>{{ d['ac_output_frequency'] }}</td></tr>
                <tr><th>Load Power</th><td>{{ d['load_power'] }}</td></tr>
                <tr><th>Battery Capacity</th><td>{{ d['battery_capacity'] }}</td></tr>
            </table>
            <p><b>Last Update:</b> {{ last }}</p>
        </body>
        </html>
    """, d=current_data, last=last_update_time,
       plant_id=current_data.get("plant_id", "N/A"),
       user_id=current_data.get("user_id", "N/A"),
       inverter_sn=current_data.get("inverter_sn", "N/A"),
       datalogger_sn=current_data.get("datalogger_sn", "N/A"),
       navigation_links=NAVIGATION_LINKS)

if __name__ == '__main__':
    threading.Thread(target=monitor_growatt).start()
    app.run(host="0.0.0.0", port=8000)
