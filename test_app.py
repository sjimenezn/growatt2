import os
import time
from datetime import datetime, timedelta
from flask import Flask

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

# --- Flask Routes ---
@app.route("/")
def home():
    log_message("Home route accessed.")
    return "<h1>Hello from Growatt Monitor (Stage 1)!</h1><p>Check console logs for messages.</p>"

@app.route("/console")
def console_view():
    # Only display the message part, not the timestamp from the tuple
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
log_message("Flask app initialized and running (Stage 1).")

