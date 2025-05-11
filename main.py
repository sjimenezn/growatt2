from flask import Flask, render_template_string, request
import requests

app = Flask(__name__)

GROWATT_USERNAME = "vospina"
PASSWORD_CRC = "0c4107c238d57d475d4660b07b2f043e"
STORAGE_SN = "BNG7CH806N"
PLANT_ID = "2817170"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest'
}

# Session to persist login
session = requests.Session()

def growatt_login():
    data = {
        'account': GROWATT_USERNAME,
        'password': '',
        'validateCode': '',
        'isReadPact': '0',
        'passwordCrc': PASSWORD_CRC
    }
    response = session.post('https://server.growatt.com/login', headers=HEADERS, data=data)
    return response.json()

def get_battery_data(date):
    payload = {
        'plantId': PLANT_ID,
        'storageSn': STORAGE_SN,
        'date': date
    }
    response = session.post('https://server.growatt.com/panel/storage/getStorageBatChart', headers=HEADERS, data=payload)
    return response.json()

@app.route('/')
def index():
    return '<h2>Growatt Monitor</h2><p>Go to <a href="/battery-chart">Battery Chart</a></p>'

@app.route('/battery-chart', methods=['GET', 'POST'])
def battery_chart():
    chart_data = []
    selected_date = ''
    if request.method == 'POST':
        selected_date = request.form['date']
        growatt_login()
        battery_json = get_battery_data(selected_date)
        chart_data = battery_json['obj']['socChart']['capacity']
    return render_template_string('''
        <html>
        <head>
            <title>Battery SoC Chart</title>
            <script src="https://code.highcharts.com/highcharts.js"></script>
        </head>
        <body>
            <h2>Select Date</h2>
            <form method="post">
                <input type="date" name="date" value="{{ selected_date }}" required>
                <button type="submit">Show Chart</button>
            </form>

            {% if chart_data %}
            <div id="chart-container" style="height: 400px; width: 100%; margin-top: 20px;"></div>
            <script>
                Highcharts.chart('chart-container', {
                    chart: { type: 'line' },
                    title: { text: 'Battery SoC on {{ selected_date }}' },
                    xAxis: {
                        title: { text: 'Time (Index)' }
                    },
                    yAxis: {
                        title: { text: 'State of Charge (%)' },
                        max: 100
                    },
                    series: [{
                        name: 'SoC',
                        data: {{ chart_data }}
                    }]
                });
            </script>
            {% endif %}
        </body>
        </html>
    ''', chart_data=chart_data, selected_date=selected_date)

# Needed for local or Docker runs
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)