import growattServer
import requests
import time

# Growatt credentials
username = "vospina"
password = "Vospina.2025"

# Telegram config
TELEGRAM_TOKEN = "7653969082:AAGJ5_P23E6SbkJnTSHOjHhUGlKwcE_hao8"
CHAT_ID = "5715745951"

# Create Growatt API instance
api = growattServer.GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0.5938.117 Mobile/15E148 Safari/604.1'
})

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

# Main monitoring function
def monitor():
    try:
        # Login
        login_response = api.login(username, password)
        print("✅ Login successful!")
        
        # Debug: Print the full login response
        print("Login response:", login_response)
        
        # Check if 'user' exists in the login response
        if 'user' not in login_response:
            raise Exception("❌ 'user' field not found in login response")
        
        # Get user ID and plant info
        user_id = login_response['user']['id']
        plant_info = api.plant_list(user_id)
        plant_id = plant_info['data'][0]['plantId']
        print("🌿 Plant ID:", plant_id)

        # Get inverter info
        inverter_list = api.inverter_list(plant_id)
        inverter_sn = inverter_list[0]['deviceSn']
        print("🔌 Inverter SN:", inverter_sn)

        while True:
            try:
                storage_data = api.storage_detail(inverter_sn)

                # Prepare the message
                message = f"""\
AC Input Voltage    : {storage_data.get('vGrid')} V
AC Input Frequency  : {storage_data.get('freqGrid')} Hz
AC Output Voltage   : {storage_data.get('outPutVolt')} V
AC Output Frequency : {storage_data.get('freqOutPut')} Hz
Battery Voltage     : {storage_data.get('vbat')} V
Active Power Output : {storage_data.get('activePower')} W
Battery Capacity    : {storage_data.get('capacity')}%
Load Percentage     : {storage_data.get('loadPercent')}%
"""
                print(message)

                # Send to Telegram
                send_telegram_message(message)

            except Exception as e_inner:
                print(f"⚠️ Error during storage fetch: {e_inner}")

            # Wait 60 seconds before next check
            time.sleep(60)

    except Exception as e_outer:
        print(f"❌ Fatal error during startup: {e_outer}")

if __name__ == "__main__":
    monitor()
