import requests
import growattServer
from datetime import datetime

# Credentials for Growatt
username = "vospina"
password = "Vospina.2025"

# Telegram Bot Token and Chat ID
telegram_token = "7653969082:AAGJ5_P23E6SbkJnTSHOjHhUGlKwcE_hao8"
chat_id = "5527163642"

# Setup Growatt API
api = growattServer.GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0.5938.117 Mobile/15E148 Safari/604.1'
})

# Main function to retrieve userId and plantId
def main():
    try:
        # Login to Growatt and get the userId and plantId
        login_response = api.login(username, password)
        print("✅ Login successful!")
        
        # Print the login response to inspect its structure
        print("Login response:", login_response)
        
        # Directly fetch userId and plantId from the login response
        user_id = login_response['userId']
        plant_info = api.plant_list(user_id)
        plant_id = plant_info['data'][0]['plantId']
        
        print(f"🌿 User ID: {user_id}")
        print(f"🌿 Plant ID: {plant_id}")
        
        # --- Send Telegram message ---
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        message = f"User ID: {user_id}\nPlant ID: {plant_id}\nTimestamp: {timestamp}"
        
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        params = {
            'chat_id': chat_id,
            'text': message
        }
        response = requests.get(url, params=params)

        if response.status_code == 200:
            print("✅ Message sent to Telegram!")
        else:
            print(f"❌ Failed to send message: {response.text}")
        # --- End of Telegram part ---

        # Stop execution after retrieving the data
        print("✅ Successfully retrieved userId and plantId. Stopping execution.")
        
    except Exception as e:
        print("❌ Error during login or data fetch.")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()