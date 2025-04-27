# Step 1: Install the growattServer library
!pip install growattServer

# Step 2: Import required modules
import growattServer
from datetime import datetime

# Step 3: Set Growatt credentials
username = "vospina"
password = "Vospina.2025"

# Step 4: Initialize the API
api = growattServer.GrowattApi()

# Step 5: Set mobile user-agent to avoid captcha
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})

# Step 6: Login and pull data
try:
    # Login
    login_response = api.login(username, password)
    print("Login successful!")

    # Extract user ID and plant ID
    user_id = login_response['user']['id']
    plant_id = 2817170

    # Get the list of devices
    devices = api.device_list(plant_id)
    print("Device List:", devices)

    # Get inverter serial number
    inverter_sn = devices[0]['deviceSn']
    print("Inverter Serial Number:", inverter_sn)

    # Try to pull storage energy overview with correct arguments
    storage_data = api.storage_energy_overview(plant_id, inverter_sn)
    print("Storage Energy Overview:")
    print(storage_data)

except Exception as e:
    print("Error:", e)
