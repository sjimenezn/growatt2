# NOTE: Full updated code based on 'gro3' with enhanced /details logging and HTML rendering.
# Telegram parts are commented out for testing.

from flask import Flask, jsonify, render_template_string
from growattServer import GrowattApi
import threading
import time
import datetime

app = Flask(__name__)
api = GrowattApi()

# --- Growatt Login Info ---
username = "your_username"
password = "your_password"

# --- Global Storage for Latest Data ---
latest_data = {
    "login_info": {},
    "plant_info": {},
    "inverter_info": {},
    "inverter_detail": {},
    "storage_energy": {},
    "storage_detail": {},
    "last_update": None
}

# --- HTML Template for /details ---
html_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Growatt Full Storage Details</title>
    <style>
        body { font-family: Arial; font-size: 22px; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; }
        th { background-color: #f2f2f2; text-align: left; }
        caption { font-size: 26px; margin-bottom: 10px; font-weight: bold; }
    </style>
</head>
<body>
    <h2>Growatt Full Storage Details</h2>
    <p><strong>Última actualización:</strong> {{ last_update }}</p>

    {% for group, values in data.items() %}
        <h3>{{ group.replace('_', ' ').title() }}</h3>
        <table>
            <tbody>
                {% for key, value in values.items() %}
                    <tr><th>{{ key }}</th><td>{{ value }}</td></tr>
                {% endfor %}
            </tbody>
        </table>
    {% endfor %}
</body>
</html>
"""

@app.route("/details")
def storage_details():
    return render_template_string(html_template, data=latest_data, last_update=latest_data["last_update"])

def fetch_all_data():
    global latest_data
    while True:
        try:
            login = api.login(username, password)
            user_id = login['user']['id']
            latest_data["login_info"] = {"user_id": user_id, "user_level": login['user'].get('userLevel')}
            print(f"{timestamp()} - 🌿 User ID: {user_id}")

            plant = api.plant_list(user_id)
            plant_id = plant['data'][0]['plantId']
            latest_data["plant_info"] = {"plant_id": plant_id}
            print(f"{timestamp()} - 🌿 Plant ID: {plant_id}")

            inverter = api.inverter_list(plant_id)
            inverter_sn = inverter[0]['deviceSn']
            latest_data["inverter_info"] = {"inverter_sn": inverter_sn}
            print(f"{timestamp()} - 🔌 Inverter SN: {inverter_sn}")

            detail = api.inverter_detail(plant_id, inverter_sn)
            latest_data["inverter_detail"] = detail.get("data", {})

            storage_energy = api.storage_energy_overview(inverter_sn)
            latest_data["storage_energy"] = storage_energy.get("obj", {})

            storage_detail = api.storage_detail(inverter_sn)
            latest_data["storage_detail"] = storage_detail.get("data", {})

            latest_data["last_update"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            print(f"{timestamp()} - ✅ Growatt login and initialization successful!")
            print(f"{timestamp()} - Updated Data: {latest_data}")

        except Exception as e:
            print(f"{timestamp()} - ❌ Error fetching Growatt data:", e)

        time.sleep(40)

def timestamp():
    return datetime.datetime.now().strftime("%H:%M:%S")

# --- Start background data thread ---
threading.Thread(target=fetch_all_data, daemon=True).start()

@app.route("/")
def home():
    return "Growatt Monitor is running. Visit /details to see full data."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)