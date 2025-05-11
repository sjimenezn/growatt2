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
            <style>
                body {
                    font-family: Arial, sans-serif;
                    text-align: center;
                    margin: 0;
                    padding: 0;
                }
                #chart-container {
                    height: 300px;  /* Adjusted chart height */
                    width: 100%;
                    margin-top: 20px;
                }
                @media (max-width: 600px) {
                    #chart-container {
                        height: 300px;  /* Set mobile chart height to 300px */
                    }
                }
                .date-picker-container {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    margin-top: 20px;
                }
                .date-picker-container input {
                    font-size: 1.5em;
                    padding: 5px;
                    text-align: center;
                }
                .date-picker-container button {
                    font-size: 1.5em;
                    padding: 5px 10px;
                    cursor: pointer;
                }
                .arrow-button {
                    font-size: 2em;
                    padding: 5px;
                    cursor: pointer;
                    background-color: transparent;
                    border: none;
                }
            </style>
        </head>
        <body>
            <h2>Select Date</h2>
            <div class="date-picker-container">
                <button class="arrow-button" onclick="changeDate(-1)">&#8592;</button>
                <form method="post" style="display: inline;">
                    <input type="date" name="date" value="{{ selected_date }}" required onchange="this.form.submit()">
                </form>
                <button class="arrow-button" onclick="changeDate(1)">&#8594;</button>
            </div>

            {% if chart_data %}
            <div id="chart-container"></div>
            <script>
                Highcharts.chart('chart-container', {
                    chart: { type: 'line' },
                    title: { text: 'Battery SoC on {{ selected_date }}' },
                    xAxis: {
                        title: { text: 'Time' },
                        categories: ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23'],
                    },
                    yAxis: {
                        title: { text: 'State of Charge (%)' },
                        max: 100,
                        min: 0,
                        tickInterval: 10,  // Reduced tick distance for Y-axis
                    },
                    series: [{
                        name: 'SoC',
                        data: {{ chart_data }},
                    }]
                });

                function changeDate(direction) {
                    const currentDate = new Date(document.querySelector('input[name="date"]').value);
                    currentDate.setDate(currentDate.getDate() + direction);
                    const formattedDate = currentDate.toISOString().split('T')[0];
                    document.querySelector('input[name="date"]').value = formattedDate;
                    document.querySelector('form').submit();
                }
            </script>
            {% endif %}
        </body>
        </html>
    ''', chart_data=chart_data, selected_date=selected_date)

# Needed for local or Docker runs
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)