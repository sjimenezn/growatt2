from flask import Flask
import threading
import time
import requests
import logging
from growattServer import GrowattApi

# Credentials
username = "vospina"
password = "Vospina.2025"

# Telegram Config
TELEGRAM_TOKEN = "7653969082:AAGJ5_P23E6SbkJnTSHOjHhUGlKwcE_hao8"
CHAT_ID = "5715745951"

# Setup Flask app
app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger()

# In-memory message log
message_log = []

# Setup Growatt API
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/91.0.4472.77 Mobile/15E148 Safari/604.1'
})

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.ok:
            log.info(f"✅ Telegram message sent: {message}")
            message_log.append(f"✅ Telegram message sent: {message}")
        else:
            log.error(f"❌ Failed to send Telegram message. Status: {response.status_code}")
            message_log.append(f"❌ Failed to send Telegram message. Status: {response.status_code}")
    except Exception as e:
        log.error(f"❌ Exception sending Telegram message: {e}")
        message_log.append(f"❌ Exception sending Telegram message: {e}")

def login_growatt():
    for attempt in range(3):  # Retry up to 3 times
        try:
            log.info(f"🔄 Attempting Growatt login (try {attempt+1})...")
            message_log.append(f"🔄 Attempting Growatt login (try {attempt+1})...")

            login_response = api.login(username, password)
            log.info(f"Login response: {login_response}")
            message_log.append(f"Login response: {login_response}")

            if not isinstance(login_response, dict) or ('userId' not in login_response and 'user' not in login_response):
                raise ValueError(f"Invalid login response structure: {login_response}")

            user_id = login_response.get('userId') or login_response['user']['id']

            plant_info = api.plant_list(user_id)
            plant_id = plant_info['data'][0]['plantId']
            inverter_info = api.inverter_list(plant_id)
            inverter_sn = inverter_info[0]['deviceSn']

            return inverter_sn

        except Exception as e:
            log.error(f"❌ Login attempt {attempt+1} failed: {e}")
            message_log.append(f"❌ Login attempt {attempt+1} failed: {e}")
            time.sleep(2)  # Wait before retry

    raise Exception("❌ All Growatt login attempts failed.")

def monitor_growatt():
    try:
        inverter_sn = login_growatt()
        log.info("✅ Growatt login and initialization successful!")
        message_log.append("✅ Growatt login and initialization successful!")

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
AC INPUT        : {ac_input_v} V / {ac_input_f} Hz
AC OUTPUT     : {ac_output_v} V / {ac_output_f} Hz
Household load : {load_w} W
Battery %      : {battery_pct} %"""

                log.info(message)
                message_log.append(message)

                if ac_input_v != "N/A" and float(ac_input_v) < 140:
                    send_telegram_message("⚠️ Low AC Input Voltage detected!\n\n" + message)

            except Exception as e_inner:
                log.error(f"⚠️ Error during monitoring: {e_inner}")
                message_log.append(f"⚠️ Error during monitoring: {e_inner}")
                log.info("🔄 Re-logging into Growatt...")
                message_log.append("🔄 Re-logging into Growatt...")
                inverter_sn = login_growatt()

            time.sleep(10)

    except Exception as e_outer:
        log.error(f"❌ Fatal monitoring error: {e_outer}")
        message_log.append(f"❌ Fatal monitoring error: {e_outer}")

@app.route("/")
def home():
    page = "✅ Growatt Monitor is Running!\n\nLogs from Python Monitoring Script:\n\n"
    page += "\n".join(message_log[-50:])  # Show last 50 log messages
    return f"<pre>{page}</pre>"

if __name__ == "__main__":
    log.info("🔄 Monitoring started, waiting for data...")
    message_log.append("🔄 Monitoring started, waiting for data...")
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
