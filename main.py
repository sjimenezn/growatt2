from flask import Flask, jsonify, request
import growattServer
import os
import logging

app = Flask(__name__)

# Set up logging to log everything
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Growatt credentials
username = "vospina"
password = "Vospina.2025"

# Create an API instance
api = growattServer.GrowattApi()

# Set a mobile Chrome on iPhone user-agent
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0.5938.117 Mobile/15E148 Safari/604.1'
})

@app.route('/')
def index():
    return "Growatt Monitoring API"

@app.route('/get_info', methods=['GET'])
def get_info():
    try:
        # Login to Growatt
        login_response = api.login(username, password)
        logger.debug(f"Login Response: {login_response}")

        if not login_response.get('success'):
            return jsonify({'error': 'Login failed'}), 400

        # Get user ID and plant info
        user_id = login_response['user']['id']
        plant_info = api.plant_list(user_id)
        logger.debug(f"Plant Info Response: {plant_info}")

        plant_id = plant_info['data'][0]['plantId']
        inverter_list = api.inverter_list(plant_id)
        inverter_sn = inverter_list[0]['deviceSn']

        # Get storage details
        storage_data = api.storage_detail(inverter_sn)
        logger.debug(f"Storage Detail Response: {storage_data}")

        parsed_data = {
            'AC Input Voltage': storage_data.get('vGrid', 'N/A'),
            'AC Input Frequency': storage_data.get('freqGrid', 'N/A'),
            'AC Output Voltage': storage_data.get('outPutVolt', 'N/A'),
            'AC Output Frequency': storage_data.get('freqOutPut', 'N/A'),
            'Battery Voltage': storage_data.get('vbat', 'N/A'),
            'Active Power Output': storage_data.get('activePower', 'N/A'),
            'Battery Capacity': storage_data.get('capacity', 'N/A'),
            'Load Percentage': storage_data.get('loadPercent', 'N/A'),
        }

        return jsonify(parsed_data)

    except Exception as e:
        logger.error(f"Error during login or data fetch: {e}")
        return jsonify({'error': f"Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))