from flask import Flask, jsonify
import threading
import time
import requests
from growattServer import GrowattApi

# Credentials
username = "vospina"
password = "Vospina.2025"

# Telegram Config
TELEGRAM_TOKEN = "7653969082:AAGJ5_P23E6SbkJnTSHOjHhUGlKwcE_hao8"
CHAT_ID = "5715745951"

# Setup Flask app
app = Flask(__name__)

# Setup Growatt API
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})

# Logs storage
logs = []

# Function to send message to Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

# Function to log data and add to logs list
def log_message(message):
    logs.append(message)
    print(message)

# Function to login to Growatt and fetch the inverter SN
def login_growatt():
    log_message("🔄 Attempting Growatt login...")
    login_response = api.login(username, password)
    plant_info = api.plant_list(login_response['user']['id'])
    plant_id = plant_info['data'][0]['plantId']
    inverter_info = api.inverter_list(plant_id)
    inverter_sn = inverter_info[0]['deviceSn']
    log_message(f"🌿 User ID: {login_response['user']['id']}")
    log_message(f"🌿 Plant ID: {plant_id}")
    return inverter_sn

# Function to monitor Growatt data
def monitor_growatt():
    active_power_threshold = 190
    sent_lights_off = False
    sent_lights_on = False

    try:
        inverter_sn = login_growatt()
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

                message = f"""\
AC INPUT          : {ac_input_v} V / {ac_input_f} Hz
AC OUTPUT      : {ac_output_v} V / {ac_output_f} Hz
Household load : {load_w} W
Battery %           : {battery_pct}"""

                log_message(message)

                if load_w != "N/A":
                    # Check if active power falls below the threshold
                    if float(load_w) < active_power_threshold and not sent_lights_off:
                        send_telegram_message("¡Se fue la luz en Acacías!\n\n" + message)
                        send_telegram_message("¡Se fue la luz en Acacías!\n\n" + message)
                        sent_lights_off = True
                        sent_lights_on = False

                    # Check if active power rises above the threshold
                    elif float(load_w) > active_power_threshold and not sent_lights_on:
                        send_telegram_message("¡Volvió la luz!\n\n" + message)
                        send_telegram_message("¡Volvió la luz!\n\n" + message)
                        sent_lights_on = True
                        sent_lights_off = False

            except Exception as e_inner:
                log_message(f"⚠️ Error during monitoring: {e_inner}")
                log_message("🔄 Re-logging into Growatt...")
                inverter_sn = login_growatt()

            time.sleep(10)

    except Exception as e_outer:
        log_message(f"❌ Fatal error: {e_outer}")

@app.route("/")
def home():
    return "✅ Growatt Monitor is Running!"

@app.route("/logs")
def get_logs():
    return jsonify({'logs': logs})

if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)