import requests
import growattServer
import time

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

# Function to send messages to Telegram with retry logic
def send_telegram_message(message, retries=3):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    
    for attempt in range(retries):
        try:
            response = requests.post(url, data=payload, timeout=10)
            response.raise_for_status()  # Check if the request was successful
            print("✅ Message sent to Telegram!")
            return  # Exit after successful message
        except Exception as e:
            print(f"❌ Failed to send message, attempt {attempt + 1}: {e}")
            if attempt < retries - 1:
                time.sleep(2)  # Wait before retrying
            else:
                print("❌ All retry attempts failed.")
                return

# Main function
def main():
    try:
        # Login to Growatt and get the userId and plantId once
        login_response = api.login(username, password)
        print("✅ Login successful!")
        
        # Print the login response to inspect its structure
        print("Login response:", login_response)
        
        # Check if 'user' field exists in the response
        if 'user' in login_response:
            user_id = login_response['user']['id']
            plant_info = api.plant_list(user_id)
            plant_id = plant_info['data'][0]['plantId']
            
            print(f"🌿 User ID: {user_id}")
            print(f"🌿 Plant ID: {plant_id}")
            
            # Create a simple message with the User ID and Plant ID
            message = f"Test message: User ID: {user_id}, Plant ID: {plant_id}"
            
            # Send the message to Telegram
            send_telegram_message(message)
            
            # Stop execution here after sending the message
            print("✅ Successfully sent a test message to Telegram. Stopping execution.")
        else:
            print("❌ 'user' field not found in login response.")
            
    except Exception as e:
        print("❌ Error during login or data fetch.")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
if __name__ == "__main__":
    main()
