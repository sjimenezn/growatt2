import requests
import growattServer
from datetime import datetime  # Add this import

# Credentials for Growatt
username = "vospina"
password = "Vospina.2025"

# Telegram Config
TELEGRAM_TOKEN = "7653969082:AAGJ5_P23E6SbkJnTSHOjHhUGlKwcE_hao8"
CHAT_ID = "5715745951"

# Setup Growatt API
api = growattServer.GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0.5938.117 Mobile/15E148 Safari/604.1'
})

# Function to send messages to Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()  # Check if the request was successful
        print("✅ Message sent to Telegram!")
    except Exception as e:
        print(f"❌ Failed to send message: {e}")

# Main function
def main():
    try:
        # Login to Growatt
        login_response = api.login(username, password)
        print("✅ Login successful!")
 
        # Create a timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Fetch userId and plantId
        user_id = login_response['userId']
        plant_info = api.plant_list(user_id)
        plant_id = plant_info['data'][0]['plantId']

        # Prepare the message with userId, plantId and timestamp
        message = (
            f"Growatt Info:\n"
            f"User ID: {user_id}\n"
            f"Plant ID: {plant_id}\n"
            f"Timestamp: {timestamp}"
        )

        # Send message
        send_telegram_message(message)

        # Fetch inverter info
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

            # Prepare message with storage data values
            storage_message = (
                f"\n⚡ Key values:\n"
                f"AC Input Voltage    : {storage_data.get('vGrid')} V\n"
                f"AC Input Frequency  : {storage_data.get('freqGrid')} Hz\n"
                f"AC Output Voltage   : {storage_data.get('outPutVolt')} V\n"
                f"AC Output Frequency : {storage_data.get('freqOutPut')} Hz\n"
                f"Battery Voltage     : {storage_data.get('vbat')} V\n"
                f"Active Power Output : {storage_data.get('activePower')} W\n"
                f"Battery Capacity    : {storage_data.get('capacity')}%\n"
                f"Load Percentage     : {storage_data.get('loadPercent')}%\n"
            )

            # Send storage data to Telegram
            send_telegram_message(storage_message)

        except Exception as e:
            print("❌ Failed to get storage_detail.")
            print("Error:", e)

        # Stop execution here after sending the message
        print("✅ Successfully sent a message to Telegram. Stopping execution.")

    except Exception as e:
        print("❌ Error during login or data fetch.")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()