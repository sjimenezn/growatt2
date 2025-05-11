import os
import tempfile
import logging
from flask import Flask, request, render_template
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    logger.debug("Starting login process.")

    # Growatt login credentials
    username = "vospina"
    password = "Vospina.2025"
    login_url = "https://server.growatt.com/login"

    # Create temp directory for Chrome profile
    chrome_user_data_dir = tempfile.mkdtemp()
    logger.debug(f"Using temp user data dir: {chrome_user_data_dir}")

    chrome_options = Options()
    chrome_options.binary_location = "/usr/bin/google-chrome"  # Fix to use google-chrome binary
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"--user-data-dir={chrome_user_data_dir}")
    chrome_options.add_argument("--disable-gpu")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(login_url)
        time.sleep(2)  # Wait for page to load

        logger.debug("Filling login form...")
        driver.find_element(By.ID, "username").send_keys(username)
        driver.find_element(By.ID, "password").send_keys(password)
        driver.find_element(By.ID, "btnLogin").click()
        time.sleep(5)  # Wait for login to complete

        logger.debug("Login attempted. Current URL: %s", driver.current_url)
        result = "Login process completed."
    except Exception as e:
        logger.exception("Error during login process")
        result = f"Login failed: {str(e)}"
    finally:
        driver.quit()

    return result

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)