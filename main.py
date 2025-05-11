from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import logging
import os

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@app.route("/")
def home():
    return "Hello from Koyeb!"

@app.route("/login")
def login():
    logger.debug("Starting login process.")

    # Setup Chrome options
    chrome_options = Options()
    chrome_binary = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    logger.debug(f"Using Chromium binary at: {chrome_binary}")
    chrome_options.binary_location = chrome_binary

    flags = [
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-software-rasterizer",
        "--disable-extensions",
        "--single-process",
        "--no-zygote"
        # Removed --user-data-dir
    ]

    for flag in flags:
        chrome_options.add_argument(flag)

    try:
        logger.debug("Creating Chrome driver...")
        driver = webdriver.Chrome(options=chrome_options)

        logger.debug("Navigating to example.com...")
        driver.get("https://example.com")
        page_title = driver.title
        logger.debug(f"Page title: {page_title}")

        driver.quit()
        return f"Logged in! Page title: {page_title}"
    except Exception as e:
        logger.error("Error during login process", exc_info=True)
        return f"Login failed: {str(e)}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)