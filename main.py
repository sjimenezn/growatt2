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

        # Log the login response to Telegram
        send_telegram_message(f"Login Response: {login_response}")

        # Get user ID and plant info
        user_id = login_response['userId']
        plant_info = api.plant_list(user_id)
        plant_id = plant_info['data'][0]['plantId']
        print(f"🌿 Plant ID: {plant_id}")

        # Log the plant info response to Telegram
        send_telegram_message(f"Plant Info Response: {plant_info}")

        # Get inverter info
        inverter_list = api.inverter_list(plant_id)
        inverter_sn = inverter_list[0]['deviceSn']
        print(f"🔌 Inverter SN: {inverter_sn}")

        # Try getting storage details
        print("\n🔍 Trying `storage_detail` (verbose)...")
        try:
            storage_data = api.storage_detail(inverter_sn)
            print("📦 Raw storage_detail response:")
            print(storage_data)  # Print full raw data for inspection

            # Log the storage detail response to Telegram
            send_telegram_message(f"Storage Detail Response: {storage_data}")

            # Parse and send parsed storage details to Telegram
            print("\n🔎 Parsed keys and values:")
            parsed_message = "\n🔎 Parsed Storage Detail:"
            for key, value in storage_data.get("data", {}).items():
                print(f"{key}: {value}")
                parsed_message += f"\n{key}: {value}"

            send_telegram_message(parsed_message)

        except Exception as e:
            print("❌ Failed to get storage_detail.")
            print("Error:", e)

            # Log the error to Telegram
            send_telegram_message(f"Error while fetching storage_detail: {e}")

    except Exception as e:
        print("❌ Error during login or data fetch.")
        print(f"Error: {e}")

        # Log the error to Telegram
        send_telegram_message(f"Error during login or data fetch: {e}")

if __name__ == "__main__":
    main()