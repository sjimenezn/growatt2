from flask import Flask, jsonify
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

# Initialize Flask app
app = Flask(__name__)
logs = []  # Global logs list

# Route to fetch and display Growatt data
@app.route('/growatt_data')
def growatt_data():
    global logs
    logs = []  # Clear logs each request
    try:
        logs.append("🔄 Attempting Growatt login...")
        login_response = api.login(username, password)
        logs.append(f"Login raw response: {repr(login_response)}")  # <- Very important!

        # Check if login_response is a dictionary
        if not isinstance(login_response, dict):
            logs.append("❌ Login response is not a dictionary. Cannot continue.")
            return jsonify({"error": "Login failed: bad response", "logs": logs})

        if login_response.get('result') != 0:
            logs.append(f"❌ Login failed with message: {login_response.get('msg')}")
            return jsonify({"error": "Login failed", "logs": logs})
        
        # Get user ID and plant info
        user_id = login_response['user']['id']
        plant_info = api.plant_list(user_id)
        plant_id = plant_info['data'][0]['plantId']

        # Get inverter info
        inverter_list = api.inverter_list(plant_id)
        inverter_sn = inverter_list[0]['deviceSn']

        # Fetch storage details
        storage_data = api.storage_detail(inverter_sn)

        logs.append("✅ Successfully fetched storage data.")

        # Return data as JSON
        return jsonify({
            'plant_id': plant_id,
            'inverter_sn': inverter_sn,
            'storage_data': storage_data.get('data', {}),
            'logs': logs
        })

    except Exception as e:
        logs.append(f"❌ Error: {str(e)}")
        return jsonify({'error': str(e), 'logs': logs}), 500


# Root route
@app.route('/')
def home():
    return "✅ Growatt Monitor is Running! Access /growatt_data to see data."

if __name__ == "__main__":
    # Run Flask app
    app.run(debug=True, host='0.0.0.0', port=8000)
