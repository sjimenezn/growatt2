from flask import Flask
import threading
import time
import requests
import logging
from io import StringIO
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

# Setup in-memory log capture (we'll capture logs to a StringIO object)
log_stream = StringIO()

# Setup Python logging to write logs to StringIO
logging.basicConfig(stream=log_stream, level=logging.INFO, format="%(asctime)s - %(message)s")

# Track monitoring status
monitoring_status = "Starting Growatt Monitor..."

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            logging.info("✅ Message sent successfully.")
        else:
            logging.warning(f"⚠️ Telegram API responded with status code {response.status_code}: {response.text}")
    except Exception as e:
        logging.error(f"❌ Failed to send Telegram message: {e}")

def login_growatt():
    logging.info("🔄 Logging into Growatt...")
    login_response = api.login(username, password)
    plant_info = api.plant_list(login_response['user']['id'])
    plant_id = plant_info['data'][0]['plantId']
    inverter_info = api.inverter_list(plant_id)
    inverter_sn = inverter_info[0]['deviceSn']
    return inverter_sn

def monitor_growatt():
    global monitoring_status
    try:
        inverter_sn = login_growatt()
        monitoring_status = "✅ Growatt Monitor is Running!"
        logging.info("✅ Growatt login and initialization successful!")

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

                logging.info(message)

                if ac_input_v != "N/A" and float(ac_input_v) < 140:
                    send_telegram_message("⚠️ Low AC Input Voltage detected!\n\n" + message)

            except Exception as e_inner:
                logging.error(f"⚠️ Error during monitoring: {e_inner}")
                logging.info("🔄 Re-logging into Growatt...")
                inverter_sn = login_growatt()

            time.sleep(10)

    except Exception as e_outer:
        monitoring_status = f"❌ Fatal error: {e_outer}"
        logging.error(f"❌ Fatal error: {e_outer}")

@app.route("/")
def home():
    # Show current monitoring status and logs
    logs = log_stream.getvalue()
    return f"""
    <h1>{monitoring_status}</h1>
    <h3>Logs:</h3>
    <pre>{logs}</pre>
    """

if __name__ == "__main__":
    threading.Thread(target=monitor_growatt, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
