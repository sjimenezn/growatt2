from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

app = Flask(__name__)

@app.route("/login-status")
def login_status():
    # Configure headless Chrome
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280x800")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://server.growatt.com/login")

        # Wait for username input to appear
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "account"))
        )

        # Fill in login form
        driver.find_element(By.ID, "account").send_keys("vospina")
        driver.find_element(By.ID, "password").send_keys("Vospina.2025")
        driver.find_element(By.CLASS_NAME, "loginBtn").click()

        # Wait for navigation after login
        WebDriverWait(driver, 10).until(
            EC.url_contains("/index")
        )

        # If URL contains /index, login is considered successful
        if "/index" in driver.current_url:
            return "Login successful!"
        else:
            return f"Login failed. Final URL: {driver.current_url}"

    except Exception as e:
        return f"An error occurred: {str(e)}"

    finally:
        driver.quit()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)