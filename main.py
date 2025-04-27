import requests
import time
from datetime import datetime
import growattServer

# Step 1: Set your Growatt credentials
username = "vospina"
password = "Vospina.2025"

# Step 2: Set the Telegram token and chat ID
telegram_token = "YOUR_BOT_TOKEN"
chat_id = "YOUR_CHAT_ID"

# Step 3: Set up the API
api = growattServer.GrowattApi()

# Step 4: Set a mobile Chrome on iPhone user-agent
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0.5938.117 Mobile/15E148 Safari/604.1'
})

# Step 5: Log in and retrieve userId and plantId
try:
    # Login
    login_response = api.login(username, password)
    print("✅ Login successful!")

    # Get user ID and plant info
    user_id = login_response['user']['id']
    plant_info = api.plant_list(user_id)
    plant_id = plant_info['data'][0]['plantId']
    
    print(f"🌿 User ID: {user_id}")
    print(f"🌿 Plant ID: {plant_id}")

    # Get current timestamp with seconds
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Step 6: Send a message to Telegram with the information
    message = f"User ID: {user_id}\nPlant ID: {plant_id}\nTimestamp: {timestamp}"
    
    # Send the message to Telegram
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

    # Stopping execution
    print("✅ Successfully sent message to Telegram. Stopping execution.")

except Exception as e:
    print("❌ Error during login or data fetch.")
    print("Error:", e)