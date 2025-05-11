import logging
from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@app.route("/")
def home():
    logger.debug("Home route accessed.")
    return "Flask app is running."

@app.route("/login-status")
def test_browser():
    logger.debug("Starting login process.")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")

    chrome_path = "/usr/bin/chromium"
    chrome_options.binary_location = chrome_path
    logger.debug(f"Using Chromium binary at: {chrome_path}")
    logger.debug(f"Chrome flags: {chrome_options.arguments}")

    try:
        logger.debug("Creating Chrome driver...")
        driver = webdriver.Chrome(options=chrome_options)

        logger.debug("Navigating to example.com...")
        driver.get("https://example.com")

        logger.debug("Page title fetched.")
        title = driver.title
        driver.quit()

        return jsonify({
            "success": True,
            "title": title,
            "message": "Login simulation ran successfully."
        })

    except WebDriverException as e:
        logger.exception("WebDriverException occurred during login simulation.")
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": e.__traceback__
        })

if __name__ == "__main__":
    logger.debug("Starting Flask app...")
    app.run(host="0.0.0.0", port=8000)