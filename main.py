from flask import Flask, jsonify
import growattServer

# Step 1: Set Growatt credentials
username = "vospina"
password = "Vospina.2025"

# Step 2: Create an API instance
api = growattServer.GrowattApi()

# Step 3: Set a mobile Chrome on iPhone user-agent
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0.5938.117 Mobile/15E148 Safari/604.1'
})

# Step 4: Initialize Flask app
app = Flask(__name__)
logs = []  # Save logs here

@app.route('/growatt_data')
def growatt_data():
    global logs
    logs = []  # Reset logs every call
    try:
        # Login
        logs.append("✅ Attempting Growatt login...")
        login_response = api.login(username, password)
        logs.append(f"Login raw response: {repr(login_response)}")

        # Correct user ID fetching
        user_id = login_response.get('user', {}).get('id')
        if not user_id:
            user_id = login_response.get('userId')  # Alternative method
        if not user_id:
            logs.append("❌ Cannot find user ID.")
            return jsonify({"error": "Cannot find user ID", "logs": logs})

        logs.append(f"🌿 User ID: {user_id}")

        # Get plant info
        plant_info = api.plant_list(user_id)
        plant_id = plant_info['data'][0]['plantId']
        logs.append(f"🌿 Plant ID: {plant_id}")

        # Get inverter info
        inverter_list = api.inverter_list(plant_id)
        inverter_sn = inverter_list[0]['deviceSn']
        logs.append(f"🔌 Inverter SN: {inverter_sn}")

        # Try getting storage details
        try:
            storage_data = api.storage_detail(inverter_sn)
            logs.append("📦 Raw storage_detail response:")
            logs.append(repr(storage_data))

            # Parsed keys and values
            for key, value in storage_data.get("data", {}).items():
                logs.append(f"{key}: {value}")

            # Pretty final values
            logs.append("\n⚡ Key values:")
            logs.append(f"AC Input Voltage    : {storage_data.get('vGrid')} V")
            logs.append(f"AC Input Frequency  : {storage_data.get('freqGrid')} Hz")
            logs.append(f"AC Output Voltage   : {storage_data.get('outPutVolt')} V")
            logs.append(f"AC Output Frequency : {storage_data.get('freqOutPut')} Hz")
            logs.append(f"Battery Voltage     : {storage_data.get('vbat')} V")
            logs.append(f"Active Power Output : {storage_data.get('activePower')} W")
            logs.append(f"Battery Capacity    : {storage_data.get('capacity')}%")
            logs.append(f"Load Percentage     : {storage_data.get('loadPercent')}%")

        except Exception as e:
            logs.append("❌ Failed to get storage_detail.")
            logs.append(f"Error: {str(e)}")

    except Exception as e:
        logs.append("❌ Error during login or data fetch.")
        logs.append(f"Error: {str(e)}")

    # Return all logs as JSON
    return jsonify({"logs": logs})

@app.route('/')
def home():
    return "✅ Growatt Monitor is Running! Access /growatt_data to see logs."

if __name__ == "__main__":
    # Run Flask app
    app.run(debug=True, host='0.0.0.0', port=8000)
