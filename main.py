from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

app = Flask(__name__)

@app.route('/login-status')
def login_status():
    try:
        # Set up headless Chrome
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        driver = webdriver.Chrome(options=options)
        driver.get("https://server.growatt.com/login")

        time.sleep(2)

        # Fill in login form
        driver.find_element(By.ID, "username").send_keys("vospina")
        driver.find_element(By.ID, "password").send_keys("Vospina.2025")
        driver.find_element(By.CLASS_NAME, "el-button--primary").click()

        time.sleep(3)

        current_url = driver.current_url
        driver.quit()

        if "/index" in current_url:
            return "Login successful!"
        else:
            return "Login failed."

    except Exception as e:
        return f"Error during login: {str(e)}"

@app.route('/')
def home():
    return 'Growatt login check app. Visit /login-status to test login.'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)