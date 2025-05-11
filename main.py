from flask import Flask, render_template_string, request
import requests
import datetime

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

@app.route('/battery-chart', methods=['GET', 'POST'])
def battery_chart():
    growatt_login()

    now_utc5 = datetime.datetime.utcnow() - datetime.timedelta(hours=5)
    selected_date = request.form.get('date') or now_utc5.strftime('%Y-%m-%d')
    battery_json = get_battery_data(selected_date)
    raw_data = battery_json.get('obj', {}).get('socChart', {}).get('capacity', [])
    
    # Pad the array to always be 288 values
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
                #chart-container { height: 60vh; width: 100%; }
                form { display: flex; align-items: center; gap: 0.5em; }
                button, input[type="date"] { font-size: 1em; }
            </style>
        </head>
        <body>
            <form method="post" id="dateForm">
                <button type="button" onclick="shiftDate(-1)">←</button>
                <input type="date" name="date" id="datePicker" value="{{ selected_date }}">
                <button type="button" onclick="shiftDate(1)">→</button>
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
                    const mm = m.toString().padStart(2, '0');
                    return h + ':' + mm;
                });

                Highcharts.chart('chart-container', {
                    chart: { type: 'line' },
                    title: { text: 'Battery SoC on {{ selected_date }}' },
                    xAxis: {
                        categories: xLabels,
                        labels: {
                            step: 12,
                            formatter: function () {
                                return this.value.slice(0, 2);  // Only hour
                            }
                        },
                        title: { text: 'Time (Hour)' }
                    },
                    yAxis: {
                        title: { text: 'State of Charge (%)' },
                        max: 100,
                        min: 0
                    },
                    tooltip: {
                        formatter: function () {
                            return `<b>${this.x}</b><br/>SoC: ${this.y}%`;
                        }
                    },
                    series: [{
                        name: 'SoC',
                        data: socData
                    }],
                    responsive: {
                        rules: [{
                            condition: { maxWidth: 600 },
                            chartOptions: {
                                chart: { height: '60%' },
                                xAxis: { labels: { step: 24 } }
                            }
                        }]
                    }
                });
            </script>
        </body>
        </html>
    ''', padded_data=padded_data, selected_date=selected_date)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)