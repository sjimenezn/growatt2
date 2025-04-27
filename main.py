import subprocess
import sys
import time

# --- Step 1: Install growattServer if not installed ---
try:
    import growattServer
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "growattServer"])
    import growattServer

# --- Step 2: Set credentials ---
username = "vospina"
password = "Vospina.2025"

# --- Step 3: Create API instance and set User-Agent ---
api = growattServer.GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0.5938.117 Mobile/15E148 Safari/604.1'
})

# --- Step 4: Login and fetch plant info ---
try:
    print("🔄 Attempting login to Growatt...")
    login_response = api.login(username, password)
    print("✅ Login successful!")

    user_id = login_response['user']['id']
    plant_info = api.plant_list(user_id)
    plant_id = plant_info['data'][0]['plantId']
    print(f"🌿 Plant ID: {plant_id}")

    inverter_list = api.inverter_list(plant_id)
    inverter_sn = inverter_list[0]['deviceSn']
    print(f"🔌 Inverter SN: {inverter_sn}")

    # --- Step 5: Try fetching storage details ---
    print("\n🔍 Trying to fetch `storage_detail`...")
    storage_data = api.storage_detail(inverter_sn)

    print("\n📦 Raw storage_detail response:")
    print(storage_data)

    print("\n🔎 Parsed keys and values:")
    for key, value in storage_data.get("data", {}).items():
        print(f"{key}: {value}")

except Exception as e:
    print("\n❌ Error during login or data fetch.")
    print("Error:", e)
