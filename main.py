from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import uuid
import traceback

app = Flask(__name__)

@app.route('/')
def home():
    return 'App is running2.'

@app.route('/login-status')
def login_status():
    try:
        chrome_options = Options()

        # Chromium flags for running in a container
        chrome_options.add_argument("--headless=new")  # Use new headless mode
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--remote-debugging-port=9222")

        # Isolate Chrome user data per session to avoid reuse conflict
        user_data_dir = f"/tmp/chrome-user-data-{uuid.uuid4()}"
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

        chrome_options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")

        # Create driver
        driver = webdriver.Chrome(options=chrome_options)

        # Navigate to Growatt login page
        driver.get("https://server.growatt.com/login")

        # Wait for login elements to be present
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "userName")))
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "password")))
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "loginBtn")))

        # Fill in login form
        driver.find_element(By.ID, "userName").send_keys("vospina")
        driver.find_element(By.ID, "password").send_keys("Vospina.2025")
        driver.find_element(By.ID, "loginBtn").click()

        # Wait for login to process (e.g., URL change or dashboard element)
        WebDriverWait(driver, 10).until(lambda d: "login" not in d.current_url)

        current_url = driver.current_url
        login_success = "login" not in current_url

        driver.quit()

        return jsonify({"login_success": login_success, "url": current_url})

    except Exception as e:
        traceback_str = traceback.format_exc()
        print(traceback_str)
        return jsonify({"error": str(e), "trace": traceback_str}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)