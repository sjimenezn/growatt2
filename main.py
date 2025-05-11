from flask import Flask, render_template_string, request
import requests
import datetime
import json

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
    session.post('https://server.growatt.com/login', headers=HEADERS, data={
        'account': GROWATT_USERNAME,
        'password': '',
        'validateCode': '',
        'isReadPact': '0',
        'passwordCrc': PASSWORD_CRC
    })

def get_battery_data(date):
    payload = {
        'plantId': PLANT_ID,
        'storageSn': STORAGE_SN,
        'date': date
    }
    res = session.post('https://server.growatt.com/panel/storage/getStorageBatChart', headers=HEADERS, data=payload)
    return res.json()

@app.route('/battery-chart', methods=['GET', 'POST'])
def battery_chart():
    growatt_login()

    utc_now = datetime.datetime.utcnow() - datetime.timedelta(hours=5)
    today_str = utc_now.strftime('%Y-%m-%d')
    selected_date = request.form.get('date') or today_str

    battery_json = get_battery_data(selected_date)
    raw_data = battery_json.get('obj', {}).get('socChart', {}).get('capacity', [])
    padded_data = raw_data + [None] * (288 - len(raw_data))

    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Battery SoC Chart</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://code.highcharts.com/highcharts.js"></script>
            <style>
                body { font-family: sans-serif; margin: 0; padding: 1em; }
                #chart-container { height: 55vh; width: 100%; margin-top: 1em; }
                .date-controls {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    gap: 1em;
                    margin-top: 1em;
                }
                .date-controls button, .date-controls input[type="date"] {
                    font-size: 1.5em;
                    padding: 0.4em 1em;
                }
                pre {
                    font-size: 0.8em;
                    white-space: pre-wrap;
                    word-break: break-word;
                    background: #f0f0f0;
                    padding: 1em;
                    margin-top: 2em;
                    overflow-x: auto;
                }
            </style>
        </head>
        <body>
            <form method="post" id="dateForm">
                <div class="date-controls">
                    <button type="button" onclick="shiftDate(-1)">←</button>
                    <input type="date" name="date" id="datePicker" value="{{ selected_date }}">
                    <button type="button" onclick="shiftDate(1)">→</button>
                </div>
            </form>

            <div id="chart-container"></div>

            <script>
                const form = document.getElementById('dateForm');
                document.getElementById('datePicker').addEventListener('change', () => form.submit());

                function shiftDate(offset) {
                    const picker = document.getElementById('datePicker');
                    const current = new Date(picker.value);
                    current.setDate(current.getDate() + offset);
                    picker.valueAsDate = current;
                    form.submit();
                }

                const socData = {{ padded_data | safe }};
                const xLabels = Array.from({length: 288}, (_, i) => {
                    const h = Math.floor(i / 12).toString().padStart(2, '0');
                    const m = (i % 12) * 5;
                    return h + ':' + m.toString().padStart(2, '0');
                });

                Highcharts.chart('chart-container', {
                    chart: {
                        type: 'line',
                        spacingTop: 10,
                        spacingBottom: 10
                    },
                    title: { text: 'Battery SoC on {{ selected_date }}' },
                    xAxis: {
                        categories: xLabels,
                        labels: {
                            step: 12,
                            formatter: function () {
                                return this.value.slice(0, 2);
                            }
                        },
                        title: { text: 'Hour of Day' }
                    },
                    yAxis: {
                        title: { text: 'State of Charge (%)' },
                        max: 100,
                        min: 0,
                        tickInterval: 20
                    },
                    tooltip: {
                        formatter: function () {
                            return `<b>${this.x}</b><br/>SoC: ${this.y ?? '—'}%`;
                        }
                    },
                    series: [{
                        name: 'SoC',
                        data: socData
                    }]
                });
            </script>

            <pre><strong>Raw Response:</strong>
{{ battery_json | tojson(indent=2) }}
            </pre>
        </body>
        </html>
    ''', padded_data=padded_data, selected_date=selected_date, battery_json=battery_json)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)