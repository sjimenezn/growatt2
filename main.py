import os
import tempfile
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
from flask import Flask, render_template, request

app = Flask(__name__)

# Function to start the Selenium login process
def login():
    try:
        # Create a unique temporary directory for user data
        temp_dir = tempfile.mkdtemp(prefix="chrome_user_data_")

        # Set up Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--no-sandbox")  # Disable sandbox (important for Docker)
        chrome_options.add_argument("--disable-gpu")  # Disable GPU acceleration (headless mode)
        chrome_options.add_argument("--disable-dev-shm-usage")  # Reduce resource consumption
        chrome_options.add_argument("--disable-software-rasterizer")  # Disable software rasterizer
        chrome_options.add_argument(f"--user-data-dir={temp_dir}")  # Point to the unique temp directory

        # Set up the Chrome driver (make sure it's compatible with your environment)
        service = Service(executable_path='/usr/bin/chromedriver')  # Ensure chromedriver is in this location
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Navigate to the Growatt login page
        driver.get("https://example.com/login")  # Replace with the actual login URL

        # Find the username and password fields and fill in credentials
        username_field = driver.find_element(By.ID, "username")  # Adjust the element's locator
        password_field = driver.find_element(By.ID, "password")  # Adjust the element's locator

        username_field.send_keys("your_username")  # Replace with your actual username
        password_field.send_keys("your_password")  # Replace with your actual password

        # Find the login button and click it
        login_button = driver.find_element(By.ID, "loginButton")  # Adjust the button's locator
        login_button.click()

        # Wait for the page to load or for some condition to be met
        time.sleep(5)  # Adjust the wait time as necessary

        # Check if login was successful
        # You can check the URL, page title, or presence of an element to confirm login
        if "dashboard" in driver.current_url:
            print("Login successful")
        else:
            print("Login failed")

        # Perform any further actions after login here...

        # Close the browser session when done
        driver.quit()

    except Exception as e:
        print(f"Error during login process: {e}")

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/login', methods=['GET', 'POST'])
def login_route():
    if request.method == 'POST':
        login()
        return "Login attempted"
    return render_template("login.html")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)