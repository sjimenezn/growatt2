from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import logging
import os

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    logger.debug("Home route accessed.")
    return "Hello from Flask with headless Chrome!"

@app.route('/login')
def login():
    logger.debug("Starting login process.")

    chrome_options = Options()
    chrome_binary = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    logger.debug(f"Using Chromium binary at: {chrome_binary}")

    flags = os.environ.get("CHROME_HEADLESS", "").split()
    logger.debug(f"Chrome flags: {flags}")
    for flag in flags:
        chrome_options.add_argument(flag)

    chrome_options.binary_location = chrome_binary

    logger.debug("Creating Chrome driver...")
    driver = webdriver.Chrome(options=chrome_options)

    logger.debug("Navigating to example.com...")
    driver.get("https://example.com")
    page_title = driver.title
    logger.debug(f"Page title: {page_title}")

    driver.quit()
    return f"Logged in! Page title: {page_title}"

if __name__ == '__main__':
    logger.debug("Starting Flask app...")
    app.run(host='0.0.0.0', port=8000)