from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

app = Flask(__name__)

@app.route("/")
def home():
    return "App is running."

@app.route("/login-status")
def login_status():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )

    driver = webdriver.Chrome(options=chrome_options)

    try:
        driver.get("https://server.growatt.com/login")
        time.sleep(3)

        # Fill in username and password
        username_input = driver.find_element(By.ID, "username")
        password_input = driver.find_element(By.ID, "password")

        username_input.send_keys("vospina")
        password_input.send_keys("Vospina.2025")

        # Click the login button
        login_button = driver.find_element(By.ID, "loginBtn")
        login_button.click()

        time.sleep(5)  # Wait for login to complete or page redirect

        current_url = driver.current_url
        if "dashboard" in current_url or "main" in current_url:
            status = "Login successful"
        else:
            status = "Login failed"

    except Exception as e:
        status = f"Error: {str(e)}"
    finally:
        driver.quit()

    return status

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)