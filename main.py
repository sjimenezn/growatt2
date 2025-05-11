from flask import Flask, render_template_string, request
import requests
from datetime import datetime, timedelta

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

session = requests.Session()

def growatt_login():
    data = {
        'account': GROWATT_USERNAME,
        'password': '',
        'validateCode': '',
        'isReadPact': '0',
        'passwordCrc': PASSWORD_CRC
    }
    return session.post('https://server.growatt.com/login', headers=HEADERS, data=data)

def get_battery_data(date):
    payload = {
        'plantId': PLANT_ID,
        'storageSn': STORAGE_SN,
        'date': date
    }
    response = session.post('https://server.growatt.com/panel/storage/getStorageBatChart', headers=HEADERS, data=payload)
    return response.json()

@app.route('/battery-chart', methods=['GET', 'POST'])
def battery_chart():
    today_local = (datetime.utcnow() - timedelta(hours=5)).strftime('%Y-%m-%d')
    selected_date = request.form.get('date', today_local)
    growatt_login()
    battery_json = get_battery_data(selected_date)
    raw_response = battery_json
    data = battery_json.get('obj', {}).get('socChart', {}).get('capacity', [])
    
    # Replace nulls with None for proper handling in JavaScript
    chart_data = [v if v is not None else None for v in data]
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Battery SoC Chart</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://code.highcharts.com/highcharts.js"></script>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 10px;
                text-align: center;
            }
            #controls {
                display: flex;
                justify-content: center;
                align-items: center;
                margin: 15px 0;
                gap: 15px;
                font-size: 2em;
            }
            #chart-container {
                height: 200px;
                width: 100%;
                margin: 0 auto;
            }
            @media (max-width: 600px) {
                #chart-container {
                    height: 150px;
                }
            }
            pre {
                text-align: left;
                font-size: 12px;
                overflow-x: auto;
                white-space: pre-wrap;
                word-wrap: break-word;
                background: #f8f8f8;
                padding: 10px;
                border: 1px solid #ccc;
            }
        </style>
    </head>
    <body>
        <h2>Battery SoC Chart</h2>
        <form method="post" id="dateForm">
            <div id="controls">
                <button type="button" onclick="changeDate(-1)">&#8592;</button>
                <input type="date" name="date" id="dateInput" value="{{ selected_date }}">
                <button type="button" onclick="changeDate(1)">&#8594;</button>
            </div>
        </form>

        <div id="chart-container"></div>

        <script>
            const chartData = {{ chart_data|tojson }};
            const baseTime = new Date("{{ selected_date }}T00:00:00Z").getTime();

            const processedData = chartData.map((val, i) => val !== null ? [baseTime + i * 5 * 60000, val] : [baseTime + i * 5 * 60000, null]);

            Highcharts.chart('chart-container', {
                chart: { type: 'line' },
                title: { text: 'Battery SoC on {{ selected_date }}' },
                xAxis: {
                    type: 'datetime',
                    labels: {
                        format: '{value:%H}',
                        step: 12
                    },
                    tickInterval: 3600 * 1000
                },
                yAxis: {
                    min: 0,
                    max: 100,
                    title: { text: 'State of Charge (%)' }
                },
                tooltip: {
                    xDateFormat: '%H:%M',
                    shared: true
                },
                series: [{
                    name: 'SoC',
                    data: processedData
                }]
            });

            function changeDate(offsetDays) {
                const input = document.getElementById("dateInput");
                const date = new Date(input.value);
                date.setDate(date.getDate() + offsetDays);
                input.valueAsDate = date;
                document.getElementById("dateForm").submit();
            }
        </script>

        <h4>Raw Response:</h4>
        <pre>{{ raw_response | tojson(indent=2) }}</pre>
    </body>
    </html>
    ''', chart_data=chart_data, selected_date=selected_date, raw_response=raw_response)

@app.route('/')
def index():
    return '<h2>Growatt Monitor</h2><p>Go to <a href="/battery-chart">Battery Chart</a></p>'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)