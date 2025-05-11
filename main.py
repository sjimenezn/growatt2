from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

app = Flask(__name__)

@app.route('/')
def home():
    return "Service is running."

@app.route('/login-status')
def login_status():
    options = Options()
    options.binary_location = "/usr/bin/chromium"
    options.add_argument("--headless=new")  # Use new headless mode
    options.add_argument("--no-sandbox")  # Required in container environments
    options.add_argument("--disable-dev-shm-usage")  # Prevents shared memory issues
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1920x1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")

    try:
        driver = webdriver.Chrome(options=options)
        driver.get("https://server.growatt.com/login")
        return "Login page loaded."
    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        try:
            driver.quit()
        except:
            pass