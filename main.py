from flask import Flask
import threading
import time
import requests
from growattServer import GrowattApi
import logging

# === CONFIGURATION ===

# Growatt Credentials
username = "vospina"
password = "Vospina.2025"

# Telegram Bot Config
TELEGRAM_TOKEN = "7653969082:AAGJ5_P23E6SbkJnTSHOjHhUGlKwcE_hao8"
CHAT_ID = "5715745951"

# === SETUP ===

# Flask App
app = Flask(__name__)

# Logger Setup
log_messages = []
def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} - {msg}"
    print(line)
    log_messages.append(line)
    if len(log_messages) > 1000:
        log_messages.pop(0)

# Growatt API with browser-like headers
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/91.0.4472.77 Mobile/15E148 Safari/604.1',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://server.growatt.com/'
})

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            log(f"✅ Telegram message sent: {message}")
        else:
            log(f"⚠️ Telegram send failed: {response.text}")
    except Exception as e:
        log(f"❌ Telegram send error: {e}")

def login_growatt():
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            log(f"🔄 Attempting Growatt login (try {attempt})...")
            login_response = api.login(username, password)
            log(f"Login response: {login_response}")

            user_id = login_response['user']['id']
            plant_info = api.plant_list(user_id)
            plant_id = plant_info['data'][0]['plantId']
            inverter_info = api.inverter_list(plant_id)
            inverter_sn = inverter_info[0]['deviceSn']

            log("✅ Growatt login and initialization successful!")
            return inverter_sn
        except Exception as e:
            log(f"❌ Login attempt {attempt} failed: {e}")
            time.sleep(3)

    raise Exception("❌ All Growatt login attempts failed.")

def monitor_growatt():
    try:
        log("🔄 Monitoring started, waiting for data...")
        inverter_sn = login_growatt()

        while True:
            try:
                data = api.storage_detail(inverter_sn)

                ac_input_v = data.get("vGrid", "N/A")
                ac_input_f = data.get("freqGrid", "N/A")
                ac_output_v = data.get("outPutVolt", "N/A")
                ac_output_f = data.get("freqOutPut", "N/A")
                load_w = data.get("activePower", "N/A")
                battery_pct = data.get("capacity", "N/A")

                message = f"""\
AC INPUT          : {ac_input_v} V / {ac_input_f} Hz
AC OUTPUT      : {ac_output_v} V / {ac_output_f} Hz
Household load : {load_w} W
Battery %           : {battery_pct}%"""

                log(message)

                if ac_input_v != "N/A" and float(ac_input_v) < 140:
                    send_telegram_message("⚠️ Low AC Input Voltage detected!\n\n" + message)

            except Exception as e_inner:
                log(f"⚠️ Error during monitoring: {e_inner}")
                log("🔄 Re-logging into Growatt...")
                inverter_sn = login_growatt()

            time.sleep(10)

    except Exception as e_outer:
        log(f"❌ Fatal monitoring error: {e_outer}")

@app.route("/")
def home():
    page = "✅ Growatt Monitor is Running!\n\nLogs from Python Monitoring Script:\n\n"
    page += "\n".join(log_messages[-30:])
    return f"<pre>{page}</pre>"

if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
