import requests
from flask import Flask, render_template, request

app = Flask(__name__)

# Route to show the login form
@app.route('/')
def index():
    return render_template('login.html')

# Route to handle login
@app.route('/login', methods=['POST'])
def login():
    # Credentials
    username = "vospina"
    password = "Vospina.2025"
    login_url = "https://server.growatt.com/login"

    # Prepare the login data (the exact field names must be matched with the form)
    data = {
        'username': username,
        'password': password
    }

    # Headers with a User-Agent to mimic a real browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
        'Content-Type': 'application/x-www-form-urlencoded',
    }

    try:
        # Create a session object to maintain cookies across requests
        session = requests.Session()

        # Perform the login request
        response = session.post(login_url, data=data, headers=headers)

        # Check if the login was successful (you can adjust the success condition)
        if response.ok and "dashboard" in response.url:
            result = "Login successful!"
        else:
            result = "Login failed or wrong credentials."

    except Exception as e:
        result = f"Error: {str(e)}"

    return result

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)