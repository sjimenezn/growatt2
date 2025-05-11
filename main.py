from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os
import time

app = Flask(__name__)

@app.route('/')
def home():
    return 'App is running.'

@app.route('/login-status')
def login_status():
    try:
        chrome_options = Options()

        # Read flags from environment and split them
        chrome_flags = os.environ.get('CHROME_FLAGS', '--headless --no-sandbox --disable-dev-shm-usage').split()
        for flag in chrome_flags:
            chrome_options.add_argument(flag)

        chrome_options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")

        # Create driver
        driver = webdriver.Chrome(options=chrome_options)

        # Navigate to Growatt login page
        driver.get("https://server.growatt.com/login")

        # Wait a bit for page to load
        time.sleep(3)

        # Fill in login form
        username_field = driver.find_element("id", "userName")
        password_field = driver.find_element("id", "password")
        login_button = driver.find_element("id", "loginBtn")

        username_field.send_keys("vospina")
        password_field.send_keys("Vospina.2025")
        login_button.click()

        time.sleep(5)  # Wait for login result

        # Check login success
        current_url = driver.current_url
        login_success = "login" not in current_url

        driver.quit()

        return jsonify({"login_success": login_success, "url": current_url})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)