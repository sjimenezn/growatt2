# Step 1: Install the growattServer library
import growattServer

# Step 2: Set your Growatt credentials
username = "vospina"
password = "Vospina.2025"

# Step 3: Create an API instance
api = growattServer.GrowattApi()

# Step 4: Set a mobile Chrome on iPhone user-agent
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0.5938.117 Mobile/15E148 Safari/604.1'
})

# Step 5: Log in and try to retrieve storage data
try:
    # Login
    login_response = api.login(username, password)
    print("✅ Login successful!")
    print("Login response:", login_response)  # Log the entire response

    # Check if 'userId' exists in the response and proceed accordingly
    if 'userId' in login_response:
        user_id = login_response['userId']  # Get userId from the response
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
    else:
        print("❌ 'userId' field not found in login response!")

except Exception as e:
    print("❌ Error during login or data fetch.")
    print("Error:", e)
