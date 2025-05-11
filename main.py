from flask import Flask, request, render_template_string, jsonify
import requests

app = Flask(__name__)

# Configuration
API_TOKEN = "08u422v880960e6cd322x8c78mc562g0"
PLANT_ID = 2817170
DEVICE_SN = "BNG7CH806N"

# Headers including Chrome user-agent
HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36")
}

@app.route('/capacity', methods=['GET'])
def capacity_page():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Battery Capacity Chart</title>
        <script src="https://code.highcharts.com/highcharts.js"></script>
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    </head>
    <body>
        <h2>Battery Capacity for Selected Date</h2>
        <label for="date">Select Date:</label>
        <input type="date" id="date" name="date">
        <button onclick="loadChart()">Load</button>
        <div id="chart" style="width:100%; height:400px;"></div>

        <script>
            function loadChart() {
                let date = document.getElementById('date').value;
                if (!date) {
                    alert("Please select a date");
                    return;
                }
                $.getJSON('/get_capacity_data?date=' + date, function(data) {
                    if (data.error) {
                        alert("Error: " + data.error);
                        return;
                    }
                    Highcharts.chart('chart', {
                        chart: { type: 'line' },
                        title: { text: 'Battery Capacity on ' + date },
                        xAxis: {
                            title: { text: 'Time (5-minute intervals)' },
                            categories: data.capacity.map((_, i) => i * 5 + ' min')
                        },
                        yAxis: {
                            title: { text: 'Capacity (%)' },
                            max: 100
                        },
                        series: [{
                            name: 'Battery Capacity',
                            data: data.capacity
                        }]
                    });
                });
            }
        </script>
    </body>
    </html>
    ''')

@app.route('/get_capacity_data')
def get_capacity_data():
    date = request.args.get('date')
    if not date:
        return jsonify({"error": "Missing date parameter"}), 400

    payload = {
        "plantId": PLANT_ID,
        "date": date,
        "jsonData": [{
            "type": "storage",
            "sn": DEVICE_SN,
            "params": "capacity"
        }]
    }

    try:
        response = requests.post(
            "https://server.growatt.com/energy/compare/getDevicesDayChart",
            headers=HEADERS,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        capacity = data.get("obj", [{}])[0].get("datas", {}).get("capacity", [])
        return jsonify({"capacity": capacity})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/test_api')
def test_api():
    return '''
    <html>
    <head><title>Test Growatt API</title></head>
    <body>
        <h2>Test Growatt API Response</h2>
        <input type="date" id="date">
        <button onclick="loadData()">Load</button>
        <pre id="result" style="white-space: pre-wrap; word-wrap: break-word;"></pre>
        <script>
            function loadData() {
                const date = document.getElementById('date').value;
                if (!date) {
                    alert("Please select a date");
                    return;
                }
                fetch('/get_capacity_data?date=' + date)
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('result').textContent = JSON.stringify(data, null, 2);
                    })
                    .catch(error => {
                        document.getElementById('result').textContent = "Error: " + error;
                    });
            }
        </script>
    </body>
    </html>
    '''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)