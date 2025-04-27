from flask import Flask
import threading
import time
import requests
from growattServer import GrowattApi
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger()

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

message_log = ["✅ Monitoring started, waiting for data..."]  # Initialize with a first message

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            log_msg = f"✅ Telegram sent successfully!\n{message}"
            log.info(log_msg)
        else:
            log_msg = f"❌ Telegram failed with status code {response.status_code}\n{message}"
            log.error(log_msg)
    except Exception as e:
        log_msg = f"❌ Telegram error: {str(e)}\n{message}"
        log.error(log_msg)
    message_log.append(log_msg)  # Save ALL message attempts to the log

def login_growatt():
    login_response = api.login(username, password)
    plant_info = api.plant_list(login_response['user']['id'])
    plant_id = plant_info['data'][0]['plantId']
    inverter_info = api.inverter_list(plant_id)
    inverter_sn = inverter_info[0]['deviceSn']
    return inverter_sn

def monitor_growatt():
    try:
        inverter_sn = login_growatt()
        log.info("✅ Growatt login and initialization successful!")
        message_log.append("✅ Growatt login successful!")

        while True:
            try:
                data = api.storage_detail(inverter_sn)

                ac_input_v = data.get("vGrid", "N/A")
                ac_input_f = data.get("freqGrid", "N/A")
                ac_output_v = data.get("outPutVolt", "N/A")
                ac_output_f = data.get("freqOutPut", "N/A")
                load_w = data.get("activePower", "N/A")
                battery_pct = data.get("capacity", "N/A")

                status_message = f"""AC INPUT: {ac_input_v} V / {ac_input_f} Hz | AC OUTPUT: {ac_output_v} V / {ac_output_f} Hz | Load: {load_w} W | Battery: {battery_pct}%"""

                log.info(status_message)
                message_log.append(status_message)

                if ac_input_v != "N/A" and float(ac_input_v) < 140:
                    send_telegram_message("⚠️ Low AC Input Voltage detected!\n\n" + status_message)

            except Exception as e_inner:
                log.error(f"⚠️ Error during monitoring: {e_inner}")
                message_log.append(f"⚠️ Error during monitoring: {e_inner}")
                log.info("🔄 Re-logging into Growatt...")
                inverter_sn = login_growatt()

            time.sleep(10)

    except Exception as e_outer:
        log.error(f"❌ Fatal error: {e_outer}")
        message_log.append(f"❌ Fatal error: {e_outer}")

@app.route("/")
def home():
    # Limit log to last 50 lines to not crash browser
    display_log = "<br>".join(message_log[-50:])
    return f"✅ Growatt Monitor is Running!<br><br>Logs from Python Monitoring Script:<br>{display_log}"

if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
