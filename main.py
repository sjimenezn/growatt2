import requests
import growattServer
from datetime import datetime

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
        
        # Log the login response
        send_telegram_message(f"Login Response: {login_response}")
        
        # Create a timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Fetch userId and plantId
        user_id = login_response['userId']
        plant_info = api.plant_list(user_id)
        
        # Log the plant info response
        send_telegram_message(f"Plant Info Response: {plant_info}")
        
        plant_id = plant_info['data'][0]['plantId']
        print("🌿 Plant ID:", plant_id)

        # Get inverter info
        inverter_list = api.inverter_list(plant_id)
        
        # Log the inverter info response
        send_telegram_message(f"Inverter List Response: {inverter_list}")
        
        inverter_sn = inverter_list[0]['deviceSn']
        print("🔌 Inverter SN:", inverter_sn)

        # Try getting storage details
        print("\n🔍 Trying `storage_detail` (verbose)...")
        try:
            storage_data = api.storage_detail(inverter_sn)
            send_telegram_message(f"Storage Detail Response: {storage_data}")
            
            print("📦 Raw storage_detail response:")
            print(storage_data)  # Print full raw data for inspection

            print("\n🔎 Parsed keys and values:")
            for key, value in storage_data.get("data", {}).items():
                print(f"{key}: {value}")

        except Exception as e:
            print("❌ Failed to get storage_detail.")
            print("Error:", e)
            send_telegram_message(f"Error during storage_detail fetch: {e}")

    except Exception as e:
        print("❌ Error during login or data fetch.")
        print(f"Error: {e}")
        send_telegram_message(f"Error during login or data fetch: {e}")

if __name__ == "__main__":
    main()