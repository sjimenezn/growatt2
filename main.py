import requests
import growattServer

# Credentials for Growatt
username = "vospina"
password = "Vospina.2025"

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
        
        # Check if 'user' field exists in the response
        if 'user' in login_response:
            user_id = login_response['user']['id']
            plant_info = api.plant_list(user_id)
            plant_id = plant_info['data'][0]['plantId']
            
            print(f"🌿 User ID: {user_id}")
            print(f"🌿 Plant ID: {plant_id}")
            
            # Stop execution here after retrieving the data
            print("✅ Successfully retrieved userId and plantId. Stopping execution.")
        else:
            print("❌ 'user' field not found in login response.")
            
    except Exception as e:
        print("❌ Error during login or data fetch.")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()