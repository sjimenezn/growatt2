# test_app.py
from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def hello():
    # This will be displayed on your Koyeb URL if it works
    return f"Hello from Gunicorn on Koyeb! Port: {os.environ.get('PORT', 'unknown')}"

# IMPORTANT: There is NO 'if __name__ == "__main__":' block here.
