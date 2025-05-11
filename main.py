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

@app.route('/test-browser')
def test_browser():
    try:
        # Auto-install matching ChromeDriver
        chromedriver_autoinstaller.install()

        chrome_options = Options()

        # Memory-safe headless configuration
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--single-process")
        chrome_options.add_argument("--remote-debugging-port=9222")

        # Explicit path (Koyeb installs here via apt)
        chrome_options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")

        # Check Chromium path exists
        assert os.path.exists(chrome_options.binary_location), f"Chromium not found at {chrome_options.binary_location}"

        driver = webdriver.Chrome(options=chrome_options)
        driver.get("https://example.com")
        title = driver.title
        driver.quit()

        return jsonify({"success": True, "title": title})

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500

@app.route('/login-status')
def login_status():
    try:
        chromedriver_autoinstaller.install()

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--single-process")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")

        assert os.path.exists(chrome_options.binary_location), f"Chromium not found at {chrome_options.binary_location}"

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
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)