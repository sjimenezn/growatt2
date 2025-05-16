@app.route("/battery-chart", methods=["GET", "POST"])
def battery_chart():
    if request.method == "POST":
        selected_date = request.form.get("date")
    else:
        selected_date = get_today_date_utc_minus_5()

    growatt_login2()

    # Request Battery SoC Data
    battery_payload = {
        'plantId': PLANT_ID,
        'storageSn': STORAGE_SN,
        'date': selected_date
    }

    try:
        battery_response = session.post(
            'https://server.growatt.com/panel/storage/getStorageBatChart',
            headers=HEADERS,
            data=battery_payload,
            timeout=10
        )
        battery_response.raise_for_status()
        battery_data = battery_response.json()
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Failed to fetch battery data for {selected_date}: {e}")
        battery_data = {}

    soc_data = battery_data.get("obj", {}).get("socChart", {}).get("capacity", [])
    if not soc_data:
        log_message(f"⚠️ No SoC data received for {selected_date}")
    soc_data = soc_data + [None] * (288 - len(soc_data))

    # Request Energy Chart Data
    energy_payload = {
        "date": selected_date,
        "plantId": PLANT_ID,
        "storageSn": STORAGE_SN
    }

    try:
        energy_response = session.post(
            "https://server.growatt.com/panel/storage/getStorageEnergyDayChart",
            headers=HEADERS,
            data=energy_payload,
            timeout=10
        )
        energy_response.raise_for_status()
        energy_data = energy_response.json()
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Failed to fetch energy chart data for {selected_date}: {e}")
        energy_data = {}

    # Access charts inside obj
    energy_obj = energy_data.get("obj", {}).get("charts", {})
    energy_titles = energy_data.get("titles", [])

    if not energy_titles or not energy_obj:
        log_message(f"⚠️ No energy chart data received for {selected_date}")

    # Format each data series for Highcharts with updated line width and color
    def prepare_series(data_list, name, color):
        if not data_list or not isinstance(data_list, list):
            return None
        return {
            "name": name,
            "data": data_list,
            "color": color,
            "fillOpacity": 0.2,
            "lineWidth": 1
        }

    # Use the requested colors for the chart (without "Exported to Grid")
    energy_series = [
        prepare_series(energy_obj.get("ppv"), "Photovoltaic Output", "#FFEB3B"),  # Yellow
        prepare_series(energy_obj.get("userLoad"), "Load Consumption", "#9C27B0"),  # Purple
        prepare_series(energy_obj.get("pacToUser"), "Imported from Grid", "#00BCD4"),  # Cyan
    ]
    energy_series = [s for s in energy_series if s and s['name'] != 'Exported to Grid']

    # Ensure 288 data points for energy data
    for series in energy_series:
        if series and series["data"]:
            series["data"] = series["data"] + [None] * (288 - len(series["data"]))
        elif series:
            series["data"] = [None] * 288

    return render_template(
        "battery-chart.html",
        selected_date=selected_date,
        soc_data=soc_data,
        raw_json=battery_data,
        energy_titles=energy_titles,
        energy_series=energy_series
    )

