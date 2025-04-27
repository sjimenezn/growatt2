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

        # Send message with timestamp
        send_telegram_message(f"Test message from Growatt monitoring script. Timestamp: {timestamp}")

        # Stop execution here after sending the message
        print("✅ Successfully sent a test message to Telegram. Stopping execution.")

    except Exception as e:
        print("❌ Error during login.")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()