from flask import Flask, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import chromedriver_autoinstaller
import os
import time
import traceback

app = Flask(__name__)

@app.route('/')
def home():
    return 'App is running.'

@app.route('/test-browser')
def test_browser():
    try:
        # Ensure correct chromedriver is installed
        chromedriver_autoinstaller.install()

        # Set up headless Chrome
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")

        # Launch browser
        driver = webdriver.Chrome(options=chrome_options)
        driver.get("https://example.com")
        time.sleep(2)  # Let the page load

        title = driver.title
        driver.quit()

        return jsonify({"success": True, "page_title": title})
    
    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"success": False, "error": str(e), "trace": tb}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)