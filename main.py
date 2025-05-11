import requests
from flask import Flask

app = Flask(__name__)

@app.route('/')
def login_and_fetch_data():
    session = requests.Session()

    # Mimic a real browser's headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36',
        'Referer': 'https://server.growatt.com/login',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    # Use correct form field names
    login_data = {
        'account': 'vospina',
        'password': 'Vospina.2025',
        'language': '1'
    }

    # Step 1: login request
    login_url = "https://server.growatt.com/login"
    response = session.post(login_url, data=login_data, headers=headers)

    if response.ok and "dashboard" in response.url:
        # Step 2: fetch data using the session
        data_url = "https://server.growatt.com/energy/compare/getDevicesDayChart"
        plant_id = 2817170
        date = "2025-05-10"
        json_data = '[{"type":"storage","sn":"BNG7CH806N","params":"capacity"}]'

        params = {
            'plantId': plant_id,
            'date': date,
            'jsonData': json_data
        }

        data_response = session.get(data_url, params=params, headers=headers)

        return f"<pre>{data_response.text}</pre>"

    return "Login failed. Response URL: " + response.url

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)