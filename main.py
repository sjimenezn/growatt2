from flask import Flask, jsonify, render_template_string
import growattServer
import requests
import time
import threading

app = Flask(__name__)

# Growatt API credentials
username = "vospina"
password = "Vospina.2025"

# Telegram credentials
telegram_token = "your-telegram-bot-token"
chat_id = "your-telegram-chat-id"

# Create an API instance
api = growattServer.GrowattApi()

# Set a mobile Chrome on iPhone user-agent
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0.5938.117 Mobile/15E148 Safari/604.1'
})

def send_to_telegram(message):
    """Function to send message to Telegram"""
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }
    try:
        response = requests.post(url, data=payload)
        print("✅ Message sent to Telegram!")
    except Exception as e:
        print("❌ Error sending message to Telegram:", e)

def get_growatt_data():
    """Fetch Growatt data and send to Telegram"""
    try:
        login_response = api.login(username, password)
        print(f"Login Response: {login_response}")

        # Get user ID and plant info
        user_id = login_response['user']['id']
        plant_info = api.plant_list(user_id)
        plant_id = plant_info['data'][0]['plantId']
        plant_name = plant_info['data'][0]['plantName']
        print(f"🌿 Plant ID: {plant_id} - {plant_name}")

        # Get inverter info
        inverter_list = api.inverter_list(plant_id)
        inverter_sn = inverter_list[0]['deviceSn']
        print(f"🔌 Inverter SN: {inverter_sn}")

        # Fetch storage details
        storage_data = api.storage_detail(inverter_sn)
        print("📦 Raw storage_detail response:")
        print(storage_data)

        message = f"""
        🌿 Plant Name: {plant_name}
        🔌 Inverter SN: {inverter_sn}

        ⚡ Key values:
        AC Input Voltage    : {storage_data.get('vGrid')} V
        AC Input Frequency  : {storage_data.get('freqGrid')} Hz
        AC Output Voltage   : {storage_data.get('outPutVolt')} V
        AC Output Frequency : {storage_data.get('freqOutPut')} Hz
        Battery Voltage     : {storage_data.get('vbat')} V
        Active Power Output : {storage_data.get('activePower')} W
        Battery Capacity    : {storage_data.get('capacity')}%
        Load Percentage     : {storage_data.get('loadPercent')}%
        """

        send_to_telegram(message)

    except Exception as e:
        print(f"❌ Error during login or data fetch: {e}")
        send_to_telegram(f"❌ Error during login or data fetch: {e}")

@app.route('/get_info')
def get_info():
    """Fetch data and return to the page"""
    try:
        login_response = api.login(username, password)
        user_id = login_response['user']['id']
        plant_info = api.plant_list(user_id)
        plant_id = plant_info['data'][0]['plantId']
        plant_name = plant_info['data'][0]['plantName']

        inverter_list = api.inverter_list(plant_id)
        inverter_sn = inverter_list[0]['deviceSn']

        storage_data = api.storage_detail(inverter_sn)

        data = {
            "Plant Name": plant_name,
            "Inverter SN": inverter_sn,
            "AC Input Voltage": storage_data.get('vGrid'),
            "AC Input Frequency": storage_data.get('freqGrid'),
            "AC Output Voltage": storage_data.get('outPutVolt'),
            "AC Output Frequency": storage_data.get('freqOutPut'),
            "Battery Voltage": storage_data.get('vbat'),
            "Active Power Output": storage_data.get('activePower'),
            "Battery Capacity": storage_data.get('capacity'),
            "Load Percentage": storage_data.get('loadPercent')
        }

        return jsonify(data)

    except Exception as e:
        print(f"❌ Error during data fetch: {e}")
        return jsonify({"error": str(e)})

def periodic_data_fetch():
    """Function to fetch data every 40 seconds"""
    while True:
        get_growatt_data()
        time.sleep(40)

@app.route('/')
def index():
    """Render the page with the formatted data"""
    return render_template_string("""
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Growatt Data</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f4f4f4;
                    text-align: center;
                    padding: 20px;
                }
                .data-container {
                    font-size: 2rem;
                    background-color: #fff;
                    padding: 20px;
                    border-radius: 10px;
                    margin: 20px 0;
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                }
                .data-container h2 {
                    margin-bottom: 20px;
                }
                .data-container div {
                    margin-bottom: 10px;
                }
                .data-container span {
                    font-weight: bold;
                }
                .refreshing {
                    font-size: 1rem;
                    margin-top: 20px;
                    color: #888;
                }
            </style>
        </head>
        <body>
            <h1>Growatt Monitoring</h1>
            <div class="data-container" id="dataContainer">
                <!-- Data will be updated here every 40 seconds -->
            </div>
            <div class="refreshing">Refreshing every 40 seconds...</div>

            <script>
                async function fetchData() {
                    const response = await fetch('/get_info');
                    const data = await response.json();
                    const dataContainer = document.getElementById('dataContainer');
                    
                    // Clear previous content
                    dataContainer.innerHTML = '';

                    // Add new data to the page
                    for (let key in data) {
                        let div = document.createElement('div');
                        div.innerHTML = `<span>${key}</span>: ${data[key]}`;
                        dataContainer.appendChild(div);
                    }
                }

                // Fetch data initially
                fetchData();

                // Set interval to fetch and update data every 40 seconds
                setInterval(fetchData, 40000);
            </script>
        </body>
        </html>
    """)

if __name__ == '__main__':
    # Start the periodic fetch in a separate thread
    threading.Thread(target=periodic_data_fetch, daemon=True).start()
    app.run(debug=True, host="0.0.0.0", port=5000)