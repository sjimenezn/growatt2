
# Step 1: Install the growattServer library
!pip install growattServer

# Step 2: Import the library
import growattServer

# Step 3: Set your Growatt credentials
username = "vospina"
password = "Vospina.2025"

# Step 4: Create an API instance
api = growattServer.GrowattApi()

# Step 5: Set a mobile Chrome on iPhone user-agent
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0.5938.117 Mobile/15E148 Safari/604.1'
})

# Step 6: Log in and try to retrieve storage data
try:
    # Login
    login_response = api.login(username, password)
    print("✅ Login successful!")

    # Get user ID and plant info
    user_id = login_response['user']['id']
    plant_info = api.plant_list(user_id)
    plant_id = plant_info['data'][0]['plantId']
    print("🌿 Plant ID:", plant_id)

    # Get inverter info
    inverter_list = api.inverter_list(plant_id)
    inverter_sn = inverter_list[0]['deviceSn']
    print("🔌 Inverter SN:", inverter_sn)

    # Try getting storage details
    print("\n🔍 Trying `storage_detail` (verbose)...")
    try:
        storage_data = api.storage_detail(inverter_sn)
        print("📦 Raw storage_detail response:")
        print(storage_data)  # Print full raw data for inspection

        print("\n🔎 Parsed keys and values:")
        for key, value in storage_data.get("data", {}).items():
            print(f"{key}: {value}")
    except Exception as e:
        print("❌ Failed to get storage_detail.")
        print("Error:", e)

except Exception as e:
    print("❌ Error during login or data fetch.")
    print("Error:", e)

    # Nicely formatted key values
print("\n⚡ Key values:")
print(f"AC Input Voltage    : {storage_data.get('vGrid')} V")
print(f"AC Input Frequency  : {storage_data.get('freqGrid')} Hz")
print(f"AC Output Voltage   : {storage_data.get('outPutVolt')} V")
print(f"AC Output Frequency : {storage_data.get('freqOutPut')} Hz")
print(f"Battery Voltage     : {storage_data.get('vbat')} V")
print(f"Active Power Output : {storage_data.get('activePower')} W")
print(f"Battery Capacity    : {storage_data.get('capacity')}%")
print(f"Load Percentage     : {storage_data.get('loadPercent')}%")

console response succesfuly with required data

Requirement already satisfied: growattServer in /usr/local/lib/python3.11/dist-packages (1.7.0)
Requirement already satisfied: requests in /usr/local/lib/python3.11/dist-packages (from growattServer) (2.32.3)
Requirement already satisfied: charset-normalizer<4,>=2 in /usr/local/lib/python3.11/dist-packages (from requests->growattServer) (3.4.1)
Requirement already satisfied: idna<4,>=2.5 in /usr/local/lib/python3.11/dist-packages (from requests->growattServer) (3.10)
Requirement already satisfied: urllib3<3,>=1.21.1 in /usr/local/lib/python3.11/dist-packages (from requests->growattServer) (2.3.0)
Requirement already satisfied: certifi>=2017.4.17 in /usr/local/lib/python3.11/dist-packages (from requests->growattServer) (2025.1.31)
✅ Login successful!
🌿 Plant ID: 2817170
🔌 Inverter SN: BNG7CH806N

🔍 Trying `storage_detail` (verbose)...
📦 Raw storage_detail response:
{'vpv2': '0', 'eBatDisChargeTotal': '75.2', 'batSn': '', 'vpv1': '199.8', 'pCharge1': '56', 'outPutPower': '49', 'pCharge2': '0', 'loadPercent': '1.6', 'apparentPower': '67', 'vbat': '49.95', 'eBatChargeToday': '2.9', 'iChargePV1': '1.1', 'freqGrid': '59.99', 'iChargePV2': '0', 'outPutVolt': '121.3', 'capacity': '97', 'freqOutPut': '60.01', 'epvToday': '2.9', 'eBatChargeTotal': '359.4', 'epvTotal': '51.2', 'vGrid': '120.5', 'eBatDisChargeToday': '0.4', 'activePower': '49'}

🔎 Parsed keys and values:

⚡ Key values:
AC Input Voltage    : 120.5 V
AC Input Frequency  : 59.99 Hz
AC Output Voltage   : 121.3 V
AC Output Frequency : 60.01 Hz
Battery Voltage     : 49.95 V
Active Power Output : 49 W
Battery Capacity    : 97%
Load Percentage     : 1.6%


