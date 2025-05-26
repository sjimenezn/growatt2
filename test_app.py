import os
import time
from datetime import datetime, timedelta
from flask import Flask, render_template_string # Added render_template_string for console
from growattServer import GrowattApi
import pprint
import json # New import for file operations
import threading # New import for threading

# --- File for saving data ---
data_file = "saved_data.json"

# Ensure the file exists and is initialized as an empty JSON array
# This block runs when the module is loaded by Gunicorn.
if not os.path.exists(data_file) or os.path.getsize(data_file) == 0:
    try:
        with open(data_file, "w") as f:
            f.write("[]")  # Initialize with an empty JSON array
        print(f"Initialized empty data file: {data_file}")
    except Exception as e:
        print(f"Error initializing data file {data_file}: {e}")

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
PLANT_ID = "2817170" # From your main.py
STORAGE_SN = "BNG7CH806N" # From your main.py

# Growatt API initialization
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})
log_message("GrowattApi object initialized with custom headers.")

# --- Shared Data for Growatt ---
fetched_data = {} # Global dictionary to store fetched Growatt data for debug view
current_data = {} # Global dictionary to store the latest processed sensor values
last_processed_time = "Never" # Time the monitor loop last ran
last_successful_growatt_update_time = "Never" # Time of last *fresh* data received from Growatt
last_saved_sensor_values = {} # Used to detect stale data from Growatt

def login_growatt():
    """
    Attempts to log into Growatt and fetch basic plant and inverter info.
    Stores results in the global 'fetched_data' dictionary.
    """
    log_message("🔄 Attempting Growatt login...")
    
    user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None # Initialize to None

    try:
        login_response = api.login(username1, password1)
        # Store only relevant parts, not the full login_response unless needed for debugging
        fetched_data['login_response_summary'] = {
            'user_id': login_response.get('user', {}).get('id'),
            'accountName': login_response.get('user', {}).get('accountName'),
            'email': login_response.get('user', {}).get('email'),
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
        inverter_data = inverter_info[0] if inverter_info else {}
        fetched_data['inverter_sn'] = inverter_data.get('deviceSn', 'N/A')
        fetched_data['datalog_sn'] = inverter_data.get('datalogSn', 'N/A')
        inverter_sn = fetched_data['inverter_sn']
        datalog_sn = fetched_data['datalog_sn']
    except Exception as e:
        log_message(f"❌ Failed to retrieve inverter info: {e}")
        return None, None, None, None
    
    if inverter_sn and inverter_sn != 'N/A':
        try:
            storage_detail = api.storage_detail(inverter_sn)
            fetched_data['initial_storage_detail'] = storage_detail
            log_message(f"✅ Initial storage detail fetched for {inverter_sn}.")
        except Exception as e:
            log_message(f"❌ Failed to retrieve initial storage detail: {e}")
            fetched_data['initial_storage_detail'] = {}
    else:
        log_message("⚠️ Inverter SN not available, skipping initial storage detail fetch.")
        fetched_data['initial_storage_detail'] = {}


    log_message(f"🌿 User ID: {user_id}, Plant ID: {plant_id}, Inverter SN: {inverter_sn}, Datalogger SN: {datalog_sn}")

    return user_id, plant_id, inverter_sn, datalog_sn

# Call login_growatt once during app startup
# These will be used by the monitor_growatt thread
GROWATT_USER_ID, GROWATT_PLANT_ID, GROWATT_INVERTER_SN, GROWATT_DATALOG_SN = login_growatt()


def save_data_to_file(data):
    global last_saved_sensor_values
    try:
        existing_data = []
        if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
            with open(data_file, "r") as f:
                try:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        log_message(f"⚠️ Warning: {data_file} did not contain a JSON list. Attempting to convert.")
                        existing_data = [existing_data]
                except json.JSONDecodeError:
                    f.seek(0)
                    lines = f.readlines()
                    existing_data = []
                    for line in lines:
                        stripped_line = line.strip()
                        if stripped_line:
                            try:
                                existing_data.append(json.loads(stripped_line))
                            except json.JSONDecodeError as e:
                                log_message(f"❌ Error decoding existing JSON line in {data_file}: {stripped_line} - {e}")
        
        # Add the new data point
        existing_data.append(data)

        # Keep only the last 1200 entries (or your desired limit)
        existing_data = existing_data[-1200:]

        # Write the entire list back as a single JSON array
        with open(data_file, "w") as f:
            json.dump(existing_data, f, indent=None, separators=(',', ':'))

        log_message("✅ Saved data to file as a JSON array.")
        
        # After successful save, update last_saved_sensor_values
        comparable_data = {k: v for k, v in data.items() if k != 'timestamp'}
        last_saved_sensor_values.update(comparable_data)

    except Exception as e:
        log_message(f"❌ Error saving data to file: {e}")


def monitor_growatt():
    global last_processed_time, last_successful_growatt_update_time, last_saved_sensor_values
    
    # Use the globally available IDs from the initial login
    user_id = GROWATT_USER_ID
    plant_id = GROWATT_PLANT_ID
    inverter_sn = GROWATT_INVERTER_SN
    datalog_sn = GROWATT_DATALOG_SN

    if not all([user_id, plant_id, inverter_sn, datalog_sn]):
        log_message("❌ Growatt IDs not available at monitor thread startup. Will attempt re-login.")
        # Ensure they are None if they failed initially
        user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None

    # On startup, attempt to populate last_saved_sensor_values from the last entry in the file
    if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
        try:
            with open(data_file, "r") as f:
                existing_data_from_file = json.load(f)
                if isinstance(existing_data_from_file, list) and existing_data_from_file:
                    last_entry = existing_data_from_file[-1]
                    last_saved_sensor_values.update({
                        'vGrid': str(last_entry.get('vGrid')) if last_entry.get('vGrid') is not None else None,
                        'outPutVolt': str(last_entry.get('outPutVolt')) if last_entry.get('outPutVolt') is not None else None,
                        'activePower': str(last_entry.get('activePower')) if last_entry.get('activePower') is not None else None,
                        'capacity': str(last_entry.get('capacity')) if last_entry.get('capacity') is not None else None,
                        'freqOutPut': str(last_entry.get('freqOutPut')) if last_entry.get('freqOutPut') is not None else None
                    })
                    log_message(f"Initialized last_saved_sensor_values from file: {last_saved_sensor_values}")
        except json.JSONDecodeError as e:
            log_message(f"⚠️ Could not load last_saved_sensor_values from {data_file} due to JSON error: {e}")
        except Exception as e:
            log_message(f"⚠️ Could not load last_saved_sensor_values from {data_file}: {e}")
    else:
        log_message("No existing data file found or it's empty. last_saved_sensor_values remains empty.")

    loop_counter = 0 # For saving data to file every X cycles

    while True:
        current_loop_datetime_utc_minus_5 = datetime.now() - timedelta(hours=5)
        current_loop_time_str = current_loop_datetime_utc_minus_5.strftime("%Y-%m-%d %H:%M:%S")

        should_save_to_file_this_cycle = False
        data_to_save_for_file = {}

        try:
            # Always attempt to (re)login and get IDs if they are missing
            if user_id is None or plant_id is None or inverter_sn is None or datalog_sn is None:
                log_message("Attempting to acquire Growatt IDs (re-login).")
                user_id, plant_id, inverter_sn, datalog_sn = login_growatt()
                if user_id is None: # If login/ID fetching fails, wait and try again
                    log_message("Growatt re-login/ID fetching failed. Retrying in 60 seconds.")
                    time.sleep(60)
                    continue # Skip to next loop iteration
            
            # Ensure inverter_sn is valid before attempting storage_detail
            if not inverter_sn or inverter_sn == 'N/A':
                log_message("❌ Inverter SN is invalid. Cannot fetch storage detail. Retrying login.")
                user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None # Force re-login
                time.sleep(60)
                continue

            raw_growatt_data = api.storage_detail(inverter_sn)
            log_message(f"Raw Growatt API data received: {raw_growatt_data}")

            new_ac_input_v = raw_growatt_data.get("vGrid", "N/A")
            new_ac_input_f = raw_growatt_data.get("freqGrid", "N/A")
            new_ac_output_v = raw_growatt_data.get("outPutVolt", "N/A")
            new_ac_output_f = raw_growatt_data.get("freqOutPut", "N/A")
            new_load_w = raw_growatt_data.get("activePower", "N/A")
            new_battery_pct = raw_growatt_data.get("capacity", "N/A")

            current_sensor_values_for_comparison = {
                "vGrid": str(new_ac_input_v),
                "outPutVolt": str(new_ac_output_v),
                "activePower": str(new_load_w),
                "capacity": str(new_battery_pct),
                "freqOutPut": str(new_ac_output_f)
            }
            
            if last_saved_sensor_values and current_sensor_values_for_comparison == last_saved_sensor_values:
                log_message("⚠️ Detected Growatt data is identical to last saved values (stale from inverter). Skipping file save.")
            else:
                log_message("✅ New Growatt data received from inverter.")
                last_successful_growatt_update_time = current_loop_time_str

                data_to_save_for_file = {
                    "timestamp": last_successful_growatt_update_time,
                    "vGrid": new_ac_input_v,
                    "outPutVolt": new_ac_output_v,
                    "activePower": new_load_w,
                    "capacity": new_battery_pct,
                    "freqOutPut": new_ac_output_f,
                }
                should_save_to_file_this_cycle = True

            current_data.update({
                "ac_input_voltage": new_ac_input_v,
                "ac_input_frequency": new_ac_input_f,
                "ac_output_voltage": new_ac_output_v,
                "ac_output_frequency": new_ac_output_f,
                "load_power": new_load_w,
                "battery_capacity": new_battery_pct,
                "user_id": user_id,
                "plant_id": plant_id,
                "inverter_sn": inverter_sn,
                "datalog_sn": datalog_sn
            })

            last_processed_time = current_loop_time_str

            # Save data to file ONLY IF should_save_to_file_this_cycle is True
            # AND it's time for the loop_counter to trigger a save.
            # Your original code has loop_counter >= 7, which means save every 8th cycle (0 to 7)
            # Assuming 40 second sleep, this is 8 * 40 = 320 seconds = ~5.3 minutes
            if should_save_to_file_this_cycle and loop_counter >= 7:
                save_data_to_file(data_to_save_for_file)
                loop_counter = 0
            elif should_save_to_file_this_cycle:
                loop_counter += 1

        except Exception as e_inner:
            log_message(f"❌ Error during Growatt data fetch or processing (API error): {e_inner}")
            user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None # Force re-login

        time.sleep(40) # Wait for 40 seconds before next API call

# Start the monitoring thread
monitor_thread = threading.Thread(target=monitor_growatt, daemon=True)
monitor_thread.start()
log_message("Growatt monitor thread started.")

# --- Flask Routes ---
@app.route("/")
def home():
    # Fetch current_data for display on the home page
    d = current_data.copy() # Use a copy to avoid issues if current_data updates during rendering
    
    return render_template_string("""
        <html>
        <head>
            <title>Growatt Monitor (Stage 4)</title>
            <meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes">
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .data-box { border: 1px solid #ccc; padding: 15px; margin-bottom: 20px; border-radius: 8px; background-color: #f9f9f9; }
                .data-item { margin-bottom: 10px; }
                .data-item strong { display: inline-block; width: 150px; }
            </style>
        </head>
        <body>
            <h1>Growatt Monitor (Stage 4)</h1>
            <p><strong>Status:</strong> Growatt monitor thread is running.</p>
            <div class="data-box">
                <h2>Current Growatt Data</h2>
                <div class="data-item"><strong>Last Processed:</strong> {{ last_processed_time }}</div>
                <div class="data-item"><strong>Last Fresh Update:</strong> {{ last_successful_growatt_update_time }}</div>
                <hr>
                <div class="data-item"><strong>AC Input Voltage:</strong> {{ d.get('ac_input_voltage', 'N/A') }} V</div>
                <div class="data-item"><strong>AC Input Frequency:</strong> {{ d.get('ac_input_frequency', 'N/A') }} Hz</div>
                <div class="data-item"><strong>AC Output Voltage:</strong> {{ d.get('ac_output_voltage', 'N/A') }} V</div>
                <div class="data-item"><strong>AC Output Frequency:</strong> {{ d.get('ac_output_frequency', 'N/A') }} Hz</div>
                <div class="data-item"><strong>Load Power:</strong> {{ d.get('load_power', 'N/A') }} W</div>
                <div class="data-item"><strong>Battery Capacity:</strong> {{ d.get('battery_capacity', 'N/A') }} %</div>
                <hr>
                <div class="data-item"><strong>User ID:</strong> {{ d.get('user_id', 'N/A') }}</div>
                <div class="data-item"><strong>Plant ID:</strong> {{ d.get('plant_id', 'N/A') }}</div>
                <div class="data-item"><strong>Inverter SN:</strong> {{ d.get('inverter_sn', 'N/A') }}</div>
                <div class="data-item"><strong>Datalogger SN:</strong> {{ d.get('datalog_sn', 'N/A') }}</div>
            </div>
            <p><a href="/console">View Console Logs & Debug Data</a></p>
        </body>
        </html>
    """,
    d=current_data,
    last_processed_time=last_processed_time,
    last_successful_growatt_update_time=last_successful_growatt_update_time
    )

@app.route("/console")
def console_view():
    log_messages_only = [m for _, m in console_logs]
    return render_template_string("""
        <html>
        <head>
            <title>Console Logs</title>
            <style>
                pre {
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }
            </style>
        </head>
        <body>
            <h2>Console Output</h2>
            <pre>{{ '\\n'.join(log_messages_only) }}</pre>
            <h2>📦 Fetched Growatt Data (Initial)</h2>
            <pre>{{ pprint.pformat(fetched_data, indent=2) }}</pre>
            <h2>⚡ Current Processed Data (from monitor thread)</h2>
            <pre>{{ pprint.pformat(current_data, indent=2) }}</pre>
            <h2>💾 Last Saved Sensor Values (for comparison)</h2>
            <pre>{{ pprint.pformat(last_saved_sensor_values, indent=2) }}</pre>
        </body>
        </html>
    """,
    pprint=pprint, # Pass pprint module to template
    console_logs=console_logs, # Pass raw logs for join in template
    fetched_data=fetched_data,
    current_data=current_data,
    last_saved_sensor_values=last_saved_sensor_values
    )

# Initial log message when the app starts
log_message("Flask app initialized and running (Stage 4).")

