import requests

# Mimic a real browser's headers
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36',
    'Referer': 'https://server.growatt.com/login',
    'Content-Type': 'application/x-www-form-urlencoded'
}

# Login data
login_data = {
    'account': 'vospina',  # Your username
    'password': '',         # Empty because the password is already encrypted
    'validateCode': '',     # Empty if no CAPTCHA is required
    'isReadPact': '0',      # Flag for reading terms
    'passwordCrc': '0c4107c238d57d475d4660b07b2f043e'  # Encrypted password CRC (same as provided)
}

# Login URL
login_url = "https://server.growatt.com/login"

# Start a session and make the POST request
with requests.Session() as session:
    response = session.post(login_url, data=login_data, headers=headers)
    
    # Print the response to see what we get
    if response.ok:
        print(f"Login response: {response.text}")
    else:
        print(f"Login failed. Response code: {response.status_code}")