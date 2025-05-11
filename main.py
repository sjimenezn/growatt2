from flask import Flask, render_template_string, request
import requests
import datetime
import pytz

app = Flask(__name__)

GROWATT_USERNAME = "vospina"
PASSWORD_CRC = "0c4107c238d57d475d4660b07b2f043e"
STORAGE_SN = "BNG7CH806N"
PLANT_ID = "2817170"

HEADERS = {
    'User-Agent': 'Mozilla/5.0',
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
    session.post('https://server.growatt.com/login', headers=HEADERS, data=data)

def get_battery_data(date):
    payload = {
        'plantId': PLANT_ID,
        'storageSn': STORAGE_SN,
        'date': date
    }
    response = session.post('https://server.growatt.com/panel/storage/getStorageBatChart', headers=HEADERS, data=payload)
    return response.json()

def get_today_date_utc_minus_5():
    now = datetime.datetime.utcnow() - datetime.timedelta(hours=5)
    return now.strftime('%Y-%m-%d')

@app.route('/battery-chart', methods=['GET', 'POST'])
def battery_chart():
    selected_date = request.form.get('date') if request.method == 'POST' else get_today_date_utc_minus_5()
    growatt_login()
    raw_json = get_battery_data(selected_date)
    soc_data = raw_json.get('obj', {}).get('socChart', {}).get('capacity', [])

    # Pad to 288 entries
    soc_data = soc_data + [None] * (288 - len(soc_data))

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Battery SoC Chart</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://code.highcharts.com/highcharts.js"></script>
        <style>
            body { font-family: sans-serif; margin: 0; padding: 0; text-align: center; }
            #controls {
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 20px;
                font-size: 24px;
                margin-top: 20px;
            }
            #controls input[type="date"] {
                font-size: 20px;
                padding: 4px;
            }
            button.arrow {
                font-size: 28px;
                background: none;
                border: none;
                cursor: pointer;
            }
            #chart-container {
                width: 100%;
                height: 35vh;
                margin-top: 10px;
            }
            pre {
                text-align: left;
                background: #eee;
                padding: 10px;
                overflow-x: scroll;
                font-size: 12px;
            }
        </style>
    </head>
    <body>
        <h2>Battery SoC Chart</h2>
        <form method="post" id="dateForm">
            <div id="controls">
                <button class="arrow" type="button" onclick="shiftDate(-1)">←</button>
                <input type="date" name="date" id="datePicker" value="{{ selected_date }}" required onchange="submitForm()">
                <button class="arrow" type="button" onclick="shiftDate(1)">→</button>
            </div>
        </form>

        <div id="chart-container"></div>

        <script>
            function submitForm() {
                document.getElementById('dateForm').submit();
            }

            function shiftDate(offset) {
                const picker = document.getElementById('datePicker');
                const current = new Date(picker.value);
                current.setDate(current.getDate() + offset);
                picker.valueAsDate = current;
                submitForm();
            }

            const socData = {{ soc_data | tojson }};
            const timeLabels = [...Array(288).keys()].map(i => {
                const h = Math.floor(i / 12).toString().padStart(2, '0');
                const m = (i % 12) * 5;
                const label = h;
                return label;
            });

            Highcharts.chart('chart-container', {
                chart: {
                    type: 'line',
                    spacingTop: 10,
                    spacingBottom: 10
                },
                title: {
                    text: 'State of Charge on {{ selected_date }}'
                },
                xAxis: {
                    categories: timeLabels,
                    tickInterval: 12, // Show every hour (12 * 5 min = 60 min)
                    title: { text: 'Hour' }
                },
                yAxis: {
                    min: 0,
                    max: 100,
                    title: { text: 'SoC (%)' }
                },
                tooltip: {
                    formatter: function () {
                        const hour = Math.floor(this.point.index / 12).toString().padStart(2, '0');
                        const minute = ((this.point.index % 12) * 5).toString().padStart(2, '0');
                        return `Time: ${hour}:${minute}<br>SoC: ${this.y}%`;
                    }
                },
                series: [{
                    name: 'SoC',
                    data: socData
                }]
            });
        </script>

    </body>
    </html>
    ''', soc_data=soc_data, selected_date=selected_date, raw_json=raw_json)

@app.route('/')
def index():
    return '<h2>Growatt Monitor</h2><p><a href="/battery-chart">View Battery Chart</a></p>'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)