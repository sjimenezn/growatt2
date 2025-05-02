# Flask Routes
@app.route("/")
def home():
    return render_template_string("""
        <html><head><title>Home - Growatt Monitor</title></head>
        <body>
            <h1>✅ Growatt Monitor is Running!</h1>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a></li>
                    <li><a href="/chatlog">Chatlog</a></li>
                    <li><a href="/console">Console</a></li>
                    <li><a href="/details">Details</a></li>
                </ul>
            </nav>
        </body></html>
    """)

@app.route("/logs")
def get_logs():
    return render_template_string("""
        <html><head><title>Growatt Monitor - Logs</title><meta http-equiv="refresh" content="40"></head>
        <body>
            <h1>Datos del Inversor</h1>
            <table border="1">
                <tr><th>AC Input Voltage</th><td>{{ d['ac_input_voltage'] }}</td></tr>
                <tr><th>AC Input Frequency</th><td>{{ d['ac_input_frequency'] }}</td></tr>
                <tr><th>AC Output Voltage</th><td>{{ d['ac_output_voltage'] }}</td></tr>
                <tr><th>AC Output Frequency</th><td>{{ d['ac_output_frequency'] }}</td></tr>
                <tr><th>Load Power</th><td>{{ d['load_power'] }}</td></tr>
                <tr><th>Battery Capacity</th><td>{{ d['battery_capacity'] }}</td></tr>
            </table>
            <p><b>Última actualización:</b> {{ last }}</p>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a></li>
                    <li><a href="/chatlog">Chatlog</a></li>
                    <li><a href="/console">Console</a></li>
                    <li><a href="/details">Details</a></li>
                </ul>
            </nav>
        </body></html>
    """, d=current_data, last=last_update_time)

@app.route("/chatlog")
def chatlog_view():
    return render_template_string("""
        <html><head><title>Growatt Monitor - Chatlog</title></head>
        <body>
            <h1>Chatlog</h1>
            <pre>{{ chat_log }}</pre>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a
