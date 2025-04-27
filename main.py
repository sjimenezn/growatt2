from flask import Flask
import threading
import time
import requests
import logging
from growattServer import GrowattApi

# === Credentials ===
username = "vospina"
password = "Vospina.2025"

# === Telegram Config ===
TELEGRAM_TOKEN = "7653969082:AAGJ5_P23E6SbkJnTSHOjHhUGlKwcE_hao8"
CHAT_ID = "5715745951"

# === Setup Flask app ===
app = Flask(__name__)

# === Setup Logging ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger()
message_log = []

# === Setup Growatt API ===
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/91.0.4472.77 Mobile/15E148 Safari/604.1'
})

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            log.info("✅ Telegram message sent successfully.")
            message_log.append("✅ Telegram message sent successfully.")
        else:
            log.error(f"❌ Telegram send failed: {response.text}")
            message_log.append(f"❌ Telegram send failed: {response.text}")
    except Exception as e:
        log.error(f"❌ Telegram send error: {e}")
        message_log.append(f"❌ Telegram send error: {e}")

def login_growatt():
    login_response = api.login(username, password)
    log.info(f"Login response: {login_response}")
    message_log.append(f"Login response: {login_response}")
    plant_info = api.plant_list(login_response['user']['id'])
    plant_id = plant_info['data'][0]['plantId']
    inverter_info = api.inverter_list(plant_id)
    inverter_sn = inverter_info[0]['deviceSn']
    return inverter_sn

def monitor_growatt():
    try:
        log.info("🔄 Monitoring started, waiting for data...")
        message_log.append("🔄 Monitoring started, waiting for data...")

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
AC INPUT          : {ac_input_v} V / {ac_input_f} Hz
AC OUTPUT      : {ac_output_v} V / {ac_output_f} Hz
Household load : {load_w} W
Battery %           : {battery_pct}"""

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
        log.error(f"❌ Fatal error: {e_outer}")
        message_log.append(f"❌ Fatal error: {e_outer}")

@app.route("/")
def home():
    log_html = "<br>".join(message_log[-50:])  # Last 50 logs only
    return f"""
    <html>
    <head><meta http-equiv="refresh" content="10"></head>
    <body>
    <h2>✅ Growatt Monitor is Running!</h2>
    <h3>Logs from Python Monitoring Script:</h3>
    <pre>{log_html}</pre>
    </body>
    </html>
    """

if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
