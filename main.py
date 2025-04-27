from flask import Flask
import threading
import time
import requests
import logging

# --- Configuration ---

# Growatt credentials
username = "vospina"
password = "Vospina.2025"

# Telegram configuration
TELEGRAM_TOKEN = "7653969082:AAGJ5_P23E6SbkJnTSHOjHhUGlKwcE_hao8"
CHAT_ID = "5715745951"

# Setup logging
log_messages = []
def add_log(message):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    entry = f"{timestamp} - {message}"
    print(entry)
    log_messages.append(entry)
    # Keep only last 50 messages
    if len(log_messages) > 50:
        log_messages.pop(0)

# --- Growatt API Class ---

class GrowattApi:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/91.0.4472.77 Mobile/15E148 Safari/604.1'
        })

    def login(self, username, password):
        url = "https://server.growatt.com/login"
        payload = {"userName": username, "password": password}
        r = self.session.post(url, data=payload, timeout=10)
        r.raise_for_status()
        return r.json()

    def plant_list(self, user_id):
        url = "https://server.growatt.com/PlantHome/GetPlantListTitle"
        payload = {"userId": user_id}
        r = self.session.post(url, data=payload, timeout=10)
        r.raise_for_status()
        return r.json()

    def inverter_list(self, plant_id):
        url = "https://server.growatt.com/PlantDevice/GetInvList"
        payload = {"plantId": plant_id}
        r = self.session.post(url, data=payload, timeout=10)
        r.raise_for_status()
        return r.json()["data"]

    def storage_detail(self, device_sn):
        url = "https://server.growatt.com/StorageDevice/GetStorageDetailBySn"
        payload = {"deviceSn": device_sn}
        r = self.session.post(url, data=payload, timeout=10)
        r.raise_for_status()
        return r.json()["obj"]

# --- Functions ---

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            add_log(f"✅ Telegram message sent successfully: {message[:50]}...")
        else:
            add_log(f"❌ Failed to send Telegram message, status: {response.status_code}, body: {response.text}")
    except Exception as e:
        add_log(f"❌ Telegram exception: {e}")

def login_growatt(api):
    for attempt in range(3):
        try:
            add_log(f"🔄 Attempting Growatt login (try {attempt+1})...")
            login_response = api.login(username, password)
            add_log(f"Login response: {login_response}")

            if login_response.get("success"):
                user_id = login_response.get("userId")
                if user_id:
                    plant_info = api.plant_list(user_id)
                    plant_id = plant_info["data"][0]["plantId"]
                    inverter_info = api.inverter_list(plant_id)
                    inverter_sn = inverter_info[0]["deviceSn"]
                    return inverter_sn
            else:
                add_log(f"❌ Growatt login failed: {login_response}")

        except Exception as e:
            add_log(f"❌ Login attempt {attempt+1} failed: {e}")

        time.sleep(3)

    raise Exception("❌ All Growatt login attempts failed.")

def monitor_growatt():
    add_log("🔄 Monitoring started, waiting for data...")
    api = GrowattApi()
    try:
        inverter_sn = login_growatt(api)
        add_log("✅ Growatt login and initialization successful!")

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

                add_log(message)

                if ac_input_v != "N/A" and float(ac_input_v) < 140:
                    send_telegram_message("⚠️ Low AC Input Voltage detected!\n\n" + message)

            except Exception as e_inner:
                add_log(f"⚠️ Monitoring error: {e_inner}")
                inverter_sn = login_growatt(api)

            time.sleep(10)

    except Exception as e_outer:
        add_log(f"❌ Fatal monitoring error: {e_outer}")

# --- Flask App ---

app = Flask(__name__)

@app.route("/")
def home():
    return (
        "<h2>✅ Growatt Monitor is Running!</h2>"
        "<h3>Logs from Python Monitoring Script:</h3>"
        "<pre>" + "\n".join(log_messages) + "</pre>"
    )

# --- Main ---

if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    add_log("🌍 Starting Flask app on port 8000...")
    app.run(host="0.0.0.0", port=8000)
