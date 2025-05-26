import os
import time
from datetime import datetime, timedelta
from flask import Flask
from growattServer import GrowattApi
import pprint

# --- Flask App ---
app = Flask(__name__)

console_logs = []

def log_message(message):
    timestamped = f"{(datetime.now() - timedelta(hours=5)).strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now = time.time()
    # Keep logs for up to 100 minutes (6000 seconds)
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 6000]

# --- Credentials ---
username1 = "vospina"
password1 = "Vospina.2025" # REMINDER: Use environment variables in production.

GROWATT_USERNAME = "vospina" # REMINDER: Consider unifying with username1.
PASSWORD_CRC = "0c4107c238d57d475d4660b07b2f043e"

# Growatt API initialization
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})
log_message("GrowattApi object initialized with custom headers.")

# --- Shared Data for Growatt ---
fetched_data = {} # Global dictionary to store fetched Growatt data

def login_growatt():
    """
    Attempts to log into Growatt and fetch basic plant and inverter info.
    Stores results in the global 'fetched_data' dictionary.
    """
    log_message("🔄 Attempting Growatt login...")
    
    user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None # Initialize to None

    try:
        login_response = api.login(username1, password1)
        fetched_data['login_response'] = {
            'user': {
                'id': login_response.get('user', {}).get('id'),
                'accountName': login_response.get('user', {}).get('accountName'),
                'email': login_response.get('user', {}).get('email'),
                # Add other specific keys you might need, but avoid storing the whole raw response
            }
        }
        user = login_response.get('user', {})
        user_id = user.get('id')
        fetched_data['user_id'] = user_id
        fetched_data['account_name'] = user.get('accountName')
        fetched_data['email'] = user.get('email')
        log_message("✅ Login successful!")
    except Exception as e:
        log_message(f"❌ Login failed: {e}")
        return None, None, None, None # Return all Nones on failure

    try:
        plant_info = api.plant_list(user_id)
        # Store only summary, avoid storing entire raw response unless absolutely needed for debugging
        if plant_info.get('data'):
            fetched_data['plant_id'] = plant_info['data'][0]['plantId']
            fetched_data['plant_name'] = plant_info['data'][0]['plantName']
            plant_id = fetched_data['plant_id']
        else:
            fetched_data['plant_id'] = 'N/A'
            fetched_data['plant_name'] = 'N/A'
            plant_id = None
    except Exception as e:
        log_message(f"❌ Failed to retrieve plant info: {e}")
        return None, None, None, None

    try:
        inverter_info = api.inverter_list(plant_id)
        # Store only summary
        inverter_data = inverter_info[0] if inverter_info else {}
        fetched_data['inverter_sn'] = inverter_data.get('deviceSn', 'N/A')
        fetched_data['datalog_sn'] = inverter_data.get('datalogSn', 'N/A')
        inverter_sn = fetched_data['inverter_sn']
        datalog_sn = fetched_data['datalog_sn']
    except Exception as e:
        log_message(f"❌ Failed to retrieve inverter info: {e}")
        return None, None, None, None
    
    # Attempt to fetch storage detail here for initial check
    if inverter_sn and inverter_sn != 'N/A': # Only try if inverter_sn was successfully retrieved
        try:
            storage_detail = api.storage_detail(inverter_sn)
            fetched_data['initial_storage_detail'] = storage_detail # Store for verification
            log_message(f"✅ Initial storage detail fetched for {inverter_sn}.")
        except Exception as e:
            log_message(f"❌ Failed to retrieve initial storage detail: {e}")
            fetched_data['initial_storage_detail'] = {} # Ensure it's present even if empty
    else:
        log_message("⚠️ Inverter SN not available, skipping initial storage detail fetch.")
        fetched_data['initial_storage_detail'] = {}


    log_message(f"🌿 User ID: {user_id}, Plant ID: {plant_id}, Inverter SN: {inverter_sn}, Datalogger SN: {datalog_sn}")

    return user_id, plant_id, inverter_sn, datalog_sn

# Call login_growatt once during app startup
# Store these globally if they are needed elsewhere consistently
GROWATT_USER_ID, GROWATT_PLANT_ID, GROWATT_INVERTER_SN, GROWATT_DATALOG_SN = login_growatt()

# --- Flask Routes ---
@app.route("/")
def home():
    log_message("Home route accessed.")
    status_msg = "Growatt API Login attempted."
    if GROWATT_USER_ID:
        status_msg += " Login successful."
    else:
        status_msg += " Login failed. See console logs for details."
    return f"<h1>Hello from Growatt Monitor (Stage 3 - Logs Fixed)!</h1><p>{status_msg}</p><p>Check console logs for Growatt data.</p>"

@app.route("/console")
def console_view():
    log_messages_only = [m for _, m in console_logs]
    return f"""
        <html>
        <head>
            <title>Console Logs</title>
            <style>
                pre {{
                    white-space: pre-wrap; /* This is the key! */
                    word-wrap: break-word;
                }}
            </style>
        </head>
        <body>
            <h2>Console Output</h2>
            <pre>{'\\n'.join(log_messages_only)}</pre>
            <h2>📦 Fetched Growatt Data (Initial)</h2>
            <pre>{pprint.pformat(fetched_data, indent=2)}</pre>
        </body>
        </html>
    """

# Initial log message when the app starts
log_message("Flask app initialized and running (Stage 3 - Logs Fixed).")

