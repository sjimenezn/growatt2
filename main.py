import os
import tempfile
import logging
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# Setup Flask
app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@app.route("/")
def index():
    return "Hello from Flask!"

@app.route("/login")
def login():
    logger.debug("Starting login process.")

    chrome_options = Options()
    chrome_binary = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    logger.debug(f"Using Chromium binary at: {chrome_binary}")

    # Create a unique temp directory for the user data
    user_data_dir = tempfile.mkdtemp()
    logger.debug(f"Temporary user data dir: {user_data_dir}")

    flags = [
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-software-rasterizer",
        "--disable-extensions",
        "--single-process",
        "--no-zygote",
        f"--user-data-dir={user_data_dir}"
    ]

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)