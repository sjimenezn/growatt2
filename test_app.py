import os
import time
from datetime import datetime, timedelta
from flask import Flask
# New imports
from growattServer import GrowattApi

# --- Flask App ---
app = Flask(__name__)

console_logs = []

def log_message(message):
    timestamped = f"{(datetime.now() - timedelta(hours=5)).strftime('%H:%M:%S')} - {message}"
    print(timestamped)
    console_logs.append((time.time(), timestamped))
    now = time.time()
    # Keep logs for up to 100 minutes (6000 seconds)
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 6000]

# --- Credentials ---
username1 = "vospina"
password1 = "Vospina.2025" # Be aware: hardcoding sensitive info is not ideal for production.
                           # Consider environment variables for real deployments.

GROWATT_USERNAME = "vospina" # This seems redundant with username1, consider unifying.
PASSWORD_CRC = "0c4107c238d57d475d4660b07b2f043e" # This is likely a hashed password or similar, used by specific Growatt login methods.

# Growatt API initialization
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
})
log_message("GrowattApi object initialized with custom headers.")

# --- Flask Routes ---
@app.route("/")
def home():
    log_message("Home route accessed.")
    return "<h1>Hello from Growatt Monitor (Stage 2)!</h1><p>Growatt API initialized. Check console logs.</p>"

@app.route("/console")
def console_view():
    log_messages_only = [m for _, m in console_logs]
    return f"""
        <html>
        <head>
            <title>Console Logs</title>
        </head>
        <body>
            <h2>Console Output</h2>
            <pre style="white-space: pre; font-family: monospace; overflow-x: auto;">{"\\n".join(log_messages_only)}</pre>
        </body>
        </html>
    """

# Initial log message when the app starts
log_message("Flask app initialized and running (Stage 2).")

