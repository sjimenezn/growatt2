from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import chromedriver_autoinstaller
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
        chromedriver_autoinstaller.install()

        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")

        driver = webdriver.Chrome(options=chrome_options)
        driver.get("https://server.growatt.com/login")
        time.sleep(3)

        driver.find_element("id", "userName").send_keys("vospina")
        driver.find_element("id", "password").send_keys("Vospina.2025")
        driver.find_element("id", "loginBtn").click()
        time.sleep(5)

        result = {
            "login_success": "login" not in driver.current_url,
            "url": driver.current_url
        }
        driver.quit()
        return jsonify(result)

    except Exception as e:
        traceback_str = traceback.format_exc()
        print(traceback_str)
        return jsonify({"error": str(e), "trace": traceback_str}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)