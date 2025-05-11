import requests
import matplotlib.pyplot as plt
from flask import Flask, render_template, request
import json

app = Flask(__name__)

# Credentials for login
username = "vospina"
password = "Vospina.2025"
login_url = "https://server.growatt.com/login"
data_url = "https://server.growatt.com/energy/compare/getDevicesDayChart"

# Headers to mimic a browser request
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded',
}

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    # Prepare the login form data with the updated input field IDs
    login_data = {
        'val_loginAccount': username,  # Updated ID for username field
        'val_loginPwd': password       # Updated ID for password field
    }

    # Create a session to maintain cookies
    session = requests.Session()

    try:
        # Send POST request to login
        response = session.post(login_url, data=login_data, headers=headers)

        # Check if login was successful
        if response.ok and "dashboard" in response.url:
            # Now that we are logged in, request the data
            plant_id = 2817170
            date = "2025-05-10"
            json_data = json.dumps([{"type": "storage", "sn": "BNG7CH806N", "params": "capacity"}])

            # Data to send in the GET request
            params = {
                'plantId': plant_id,
                'date': date,
                'jsonData': json_data
            }

            data_response = session.get(data_url, params=params, headers=headers)

            # Check if we received a valid response
            if data_response.ok:
                data = data_response.json()
                # Extract capacity data
                capacity_data = data['obj'][0]['datas']['capacity']

                # Plot the data using Matplotlib
                plt.plot(capacity_data)
                plt.title('Capacity over Time')
                plt.xlabel('Time (hours)')
                plt.ylabel('Capacity (%)')
                plt.show()

                return "Login and data retrieval successful. Data plotted."
            else:
                return "Failed to fetch data after login."

        else:
            return "Login failed."

    except Exception as e:
        return f"An error occurred: {str(e)}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)