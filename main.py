from flask import Flask, jsonify
import growattServer

# Global variable to store logs
logs = []

# Step 3: Set your Growatt credentials
username = "vospina"
password = "Vospina.2025"

# Step 4: Create an API instance using growattServer
api = growattServer.GrowattApi()

# Step 5: Set a mobile Chrome on iPhone user-agent
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0.5938.117 Mobile/15E148 Safari/604.1'
})

# Initialize Flask app
app = Flask(__name__)

# Route to fetch and display Growatt data
@app.route('/growatt_data')
def growatt_data():
    try:
        logs.append("🔄 Attempting Growatt login...")
        
        # Login to Growatt API using the growattServer library
        login_response = api.login(username, password)
        
        if login_response['result'] != 0:
            logs.append(f"❌ Login failed: {login_response['msg']}")
            return jsonify({'error': 'Login failed', 'message': login_response['msg']}), 400
        
        logs.append("✅ Login successful!")

        # Get user ID and plant info using the growattServer library
        user_id = login_response['user']['id']
        plant_info = api.plant_list(user_id)
        plant_id = plant_info['data'][0]['plantId']
        logs.append(f"🌿 Plant ID: {plant_id}")

        # Get inverter info using the growattServer library
        inverter_list = api.inverter_list(plant_id)
        inverter_sn = inverter_list[0]['deviceSn']
        logs.append(f"🔌 Inverter SN: {inverter_sn}")

        # Fetch storage details using the growattServer library
        storage_data = api.storage_detail(inverter_sn)
        logs.append("🔍 Storage data fetched successfully.")

        # Return data as JSON and also display logs
        return jsonify({
            'plant_id': plant_id,
            'inverter_sn': inverter_sn,
            'storage_data': storage_data.get('data', {}),
            'logs': logs
        })

    except Exception as e:
        logs.append(f"❌ Error: {str(e)}")
        return jsonify({'error': str(e), 'logs': logs}), 500

# Start the Flask app
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=8000)
