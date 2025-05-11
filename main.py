from flask import Flask
import requests

app = Flask(__name__)

# Global session to maintain cookies
session = requests.Session()

# Common headers
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest',
    'Origin': 'https://server.growatt.com',
    'Referer': 'https://server.growatt.com/login',
    'Accept': 'application/json, text/javascript, */*; q=0.01'
}

login_data = {
    'account': 'vospina',
    'password': '',
    'validateCode': '',
    'isReadPact': '0',
    'passwordCrc': '0c4107c238d57d475d4660b07b2f043e'
}

@app.route('/')
def login_status():
    login_url = 'https://server.growatt.com/login'
    response = session.post(login_url, data=login_data, headers=headers)

    if response.ok and response.json().get('result') == 1:
        return "Login successful!"
    else:
        return f"Login failed. Response: {response.text}"

@app.route('/battery-data')
def battery_data():
    # Ensure we're logged in
    login_url = 'https://server.growatt.com/login'
    login_response = session.post(login_url, data=login_data, headers=headers)

    if not (login_response.ok and login_response.json().get('result') == 1):
        return "Login failed. Cannot fetch battery data."

    post_url = "https://server.growatt.com/panel/storage/getStorageBatChart"
    payload = {
        'plantId': '2817170',
        'storageSn': 'BNG7CH806N',
        'date': '2025-05-10'
    }

    data_response = session.post(post_url, data=payload, headers=headers)

    if data_response.ok:
        return f"<pre>{data_response.text}</pre>"
    else:
        return f"Data request failed. Status: {data_response.status_code}"

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)