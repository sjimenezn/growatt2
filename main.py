import time
import growattServer
import requests
from flask import Flask, jsonify
import threading

app = Flask(__name__)

# Set your Growatt credentials
username = "vospina"
password = "Vospina.2025"
api = growattServer.GrowattApi()

# Set the mobile Chrome user-agent
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0.5938.117 Mobile/15E148 Safari/604.1'
})

# Your Telegram bot token and chat ID
telegram_token = "your-telegram-bot-token"
chat_id = "your-chat-id"


# Function to login to Growatt and fetch the data
def fetch_data():
    try:
        # Login to Growatt
        login_response = api.login(username, password)
        print("✅ Login successful!")

        # Get user ID and plant info
        user_id = login_response['user']['id']
        plant_info = api.plant_list(user_id)
        plant_id = plant_info['data'][0]['plantId']
        print(f"🌿 Plant ID: {plant_id}")

        # Get inverter info
        inverter_list = api.inverter_list(plant_id)
        inverter_sn = inverter_list[0]['deviceSn']
        print(f"🔌 Inverter SN: {inverter_sn}")

        # Get storage details
        storage_data = api.storage_detail(inverter_sn)
        print("\n🔎 Parsed keys and values:")
        
        # Format the data as requested
        formatted_data = {
            "AC Input Voltage": f"{storage_data.get('vGrid', 'N/A')} V",
            "AC Input Frequency": f"{storage_data.get('freqGrid', 'N/A')} Hz",
            "AC Output Voltage": f"{storage_data.get('outPutVolt', 'N/A')} V",
            "AC Output Frequency": f"{storage_data.get('freqOutPut', 'N/A')} Hz",
            "Battery Voltage": f"{storage_data.get('vbat', 'N/A')} V",
            "Active Power Output": f"{storage_data.get('activePower', 'N/A')} W",
            "Battery Capacity": f"{storage_data.get('capacity', 'N/A')}%",
            "Load Percentage": f"{storage_data.get('loadPercent', 'N/A')}%"
        }
        
        # Print formatted data to console
        print("📊 Formatted Data:")
        for key, value in formatted_data.items():
            print(f"{key}: {value}")
        
        return formatted_data

    except Exception as e:
        print("❌ Error during login or data fetch.")
        print("Error:", e)
        return None


# Function to send data to Telegram
def send_to_telegram(data):
    message = "\n".join([f"{key}: {value}" for key, value in data.items()])
    telegram_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    params = {
        'chat_id': chat_id,
        'text': message
    }
    try:
        response = requests.get(telegram_url, params=params)
        if response.status_code == 200:
            print("✅ Message sent to Telegram!")
        else:
            print("❌ Failed to send message to Telegram!")
    except Exception as e:
        print(f"❌ Error sending message to Telegram: {e}")


# Function to periodically fetch data and send to Telegram every 40 seconds
def periodic_task():
    while True:
        data = fetch_data()
        if data:
            send_to_telegram(data)
        time.sleep(40)  # Wait for 40 seconds before sending again


@app.route('/')
def home():
    return "Growatt Monitoring API is running!"


@app.route('/get_info', methods=['GET'])
def get_info():
    data = fetch_data()
    if data:
        return jsonify(data)
    else:
        return jsonify({"error": "Failed to fetch data"}), 500


if __name__ == "__main__":
    # Start the periodic task in a separate thread
    threading.Thread(target=periodic_task, daemon=True).start()

    # Run Flask app
    app.run(debug=True, host="0.0.0.0", port=5000)