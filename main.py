import logging
from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os
import time
import traceback

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    logger.debug("Home route accessed.")
    return 'App is running.'

@app.route('/login-status')
def login_status():
    try:
        logger.debug("Starting login process.")

        chrome_options = Options()

        # Read flags from environment and split them
        chrome_flags = os.environ.get('CHROME_FLAGS', '--headless --no-sandbox --disable-dev-shm-usage').split()
        logger.debug(f"Chrome flags: {chrome_flags}")
        for flag in chrome_flags:
            chrome_options.add_argument(flag)

        chrome_options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
        logger.debug(f"Using Chromium binary at: {chrome_options.binary_location}")

        # Create driver
        logger.debug("Creating Chrome driver...")
        driver = webdriver.Chrome(options=chrome_options)

        # Navigate to Growatt login page
        logger.debug("Navigating to Growatt login page.")
        driver.get("https://server.growatt.com/login")

        # Wait a bit for page to load
        logger.debug("Waiting for page to load.")
        time.sleep(3)

        # Fill in login form
        username_field = driver.find_element("id", "userName")
        password_field = driver.find_element("id", "password")
        login_button = driver.find_element("id", "loginBtn")

        logger.debug("Filling in credentials.")
        username_field.send_keys("vospina")
        password_field.send_keys("Vospina.2025")
        login_button.click()

        # Wait for login result
        logger.debug("Waiting for login result.")
        time.sleep(5)

        # Check login success
        current_url = driver.current_url
        login_success = "login" not in current_url
        logger.debug(f"Login success: {login_success}, Current URL: {current_url}")

        driver.quit()

        return jsonify({"login_success": login_success, "url": current_url})

    except Exception as e:
        # Log exception with traceback
        traceback_str = traceback.format_exc()
        logger.error(f"Error occurred: {str(e)}")
        logger.error(f"Traceback: {traceback_str}")
        return jsonify({"error": str(e), "trace": traceback_str}), 500

@app.route('/test-browser')
def test_browser():
    try:
        logger.debug("Testing browser with headless Chromium.")
        chrome_options = Options()
        chrome_flags = os.environ.get('CHROME_FLAGS', '--headless --no-sandbox --disable-dev-shm-usage').split()
        for flag in chrome_flags:
            chrome_options.add_argument(flag)

        chrome_options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
        logger.debug(f"Using Chromium binary at: {chrome_options.binary_location}")

        driver = webdriver.Chrome(options=chrome_options)

        logger.debug("Navigating to a simple website to test the browser.")
        driver.get("https://www.example.com")

        # Wait for page load
        time.sleep(3)
        
        current_url = driver.current_url
        logger.debug(f"Test browser page loaded. Current URL: {current_url}")

        driver.quit()

        return jsonify({"success": True, "url": current_url})

    except Exception as e:
        traceback_str = traceback.format_exc()
        logger.error(f"Error occurred in test browser: {str(e)}")
        logger.error(f"Traceback: {traceback_str}")
        return jsonify({"error": str(e), "trace": traceback_str}), 500

if __name__ == '__main__':
    logger.debug("Starting Flask app...")
    app.run(host="0.0.0.0", port=8000)