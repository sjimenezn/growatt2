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
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": chat_id, "text": message}
            requests.post(url, data=payload, timeout=10)
        except Exception as e:
            log_message(f"❌ Failed to send message to {chat_id}: {e}")

# Navigation bar for all pages
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
            <h1>Growatt Monitor</h1>
            {NAVIGATION_LINKS}
            <p>Welcome to the Growatt Monitor!</p>
        </body>
        </html>
    """)

@app.route("/logs")
def get_logs():
    return render_template_string(f"""
        <html>
        <head><title>Growatt Monitor - Logs</title><meta http-equiv="refresh" content="40"></head>
        <body>
            <h1>Logs</h1>
            {NAVIGATION_LINKS}
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
    """, d=current_data, last=last_update_time)

@app.route("/chatlog")
def chatlog_view():
    return render_template_string(f"""
        <html>
        <head><title>Growatt Monitor - Chat Log</title></head>
        <body>
            <h1>Chat Logs</h1>
            {NAVIGATION_LINKS}
            <pre>{{ logs }}</pre>
        </body>
        </html>
    """, logs="\n".join(map(str, chat_log)))

@app.route("/console")
def console_view():
    return render_template_string(f"""
        <html>
        <head><title>Growatt Monitor - Console Logs</title><meta http-equiv="refresh" content="10"></head>
        <body>
            <h1>Console Logs</h1>
            {NAVIGATION_LINKS}
            <pre>{{ logs }}</pre>
        </body>
        </html>
    """, logs="\n".join(m for _, m in console_logs))

@app.route("/details")
def details_view():
    return render_template_string(f"""
        <html>
        <head><title>Growatt Monitor - Details</title><meta http-equiv="refresh" content="40"></head>
        <body>
            <h1>Details</h1>
            {NAVIGATION_LINKS}
            <h2>Constant Information</h2>
            <p>Plant ID: {{ plant_id }}</p>
            <p>User ID: {{ user_id }}</p>
            <p>Inverter SN: {{ inverter_sn }}</p>
            <p>Datalogger SN: {{ datalogger_sn }}</p>
            <h2>Real-Time Data</h2>
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
       datalogger_sn=current_data.get("datalogger_sn", "N/A"))

if __name__ == '__main__':
    threading.Thread(target=log_message, args=("Monitoring started",)).start()
    app.run(host="0.0.0.0", port=8000)
