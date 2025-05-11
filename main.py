from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

app = Flask(__name__)

@app.route("/")
def index():
    return "Growatt Login Status Checker"

@app.route("/login-status")
def login_status():
    # Set up Chrome options for headless mode in Docker
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    options.binary_location = "/usr/bin/chromium"

    # Start Chrome WebDriver
    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://server.growatt.com/login")
        time.sleep(2)  # wait for the page to load

        # Fill in login fields (replace with your actual credentials)
        username_input = driver.find_element(By.ID, "account")
        password_input = driver.find_element(By.ID, "password")

        username_input.send_keys("your_username_here")
        password_input.send_keys("your_password_here")

        # Click the login button
        login_button = driver.find_element(By.CLASS_NAME, "login-btn")
        login_button.click()

        time.sleep(5)  # wait for redirect

        # Check login success
        if "dashboard" in driver.current_url:
            status = "Login successful"
        else:
            status = "Login failed or redirected to unexpected page"

        return jsonify({"status": status})

    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)}), 500

    finally:
        driver.quit()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)