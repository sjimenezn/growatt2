from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os
import time
import traceback

app = Flask(__name__)

@app.route('/')
def home():
    return 'App is running.'

@app.route('/login-status')
def login_status():
    try:
        chrome_options = Options()
        chrome_flags = os.environ.get(
            'CHROME_FLAGS',
            '--headless --no-sandbox --disable-dev-shm-usage --user-data-dir=/tmp/chrome-profile'
        ).split()
        for flag in chrome_flags:
            chrome_options.add_argument(flag)

        chrome_options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")

        driver = webdriver.Chrome(options=chrome_options)

        driver.get("https://server.growatt.com/login")
        time.sleep(3)

        username_field = driver.find_element("id", "userName")
        password_field = driver.find_element("id", "password")
        login_button = driver.find_element("id", "loginBtn")

        username_field.send_keys("vospina")
        password_field.send_keys("Vospina.2025")
        login_button.click()

        time.sleep(5)

        current_url = driver.current_url
        login_success = "login" not in current_url

        driver.quit()

        return jsonify({"login_success": login_success, "url": current_url})
    except Exception as e:
        traceback_str = traceback.format_exc()
        print(traceback_str)
        return jsonify({"error": str(e), "trace": traceback_str}), 500

@app.route('/test-browser')
def test_browser():
    try:
        chrome_options = Options()
        chrome_flags = os.environ.get(
            'CHROME_FLAGS',
            '--headless --no-sandbox --disable-dev-shm-usage --user-data-dir=/tmp/chrome-profile'
        ).split()
        for flag in chrome_flags:
            chrome_options.add_argument(flag)

        chrome_options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")

        driver = webdriver.Chrome(options=chrome_options)
        driver.get("https://example.com")
        title = driver.title
        driver.quit()
        return jsonify({"success": True, "title": title})
    except Exception as e:
        traceback_str = traceback.format_exc()
        print(traceback_str)
        return jsonify({"error": str(e), "trace": traceback_str, "success": False}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)