from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

app = Flask(__name__)

@app.route('/login-test')
def login_test():
    options = Options()
    options.headless = True
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.5481.100 Safari/537.36")

    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://server.growatt.com/login")  # Replace with actual login URL

        # Fill in login details
        username_input = driver.find_element(By.NAME, "username")
        password_input = driver.find_element(By.NAME, "password")
        username_input.send_keys("vospina")
        password_input.send_keys("Vospina.2025")

        # Click login button
        driver.find_element(By.CLASS_NAME, "login100-form-btn").click()

        # Wait for page to load
        time.sleep(3)

        # Check if redirected to dashboard or /index
        if "/index" in driver.current_url or "dashboard" in driver.page_source.lower():
            return "Login successful"
        else:
            return "Login failed"
    except Exception as e:
        return f"Error during login: {str(e)}"
    finally:
        driver.quit()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)