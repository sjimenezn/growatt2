 # Try getting storage details
    print("\n🔍 Trying `storage_detail` (verbose)...")
    try:
        storage_data = api.storage_detail(inverter_sn)
        print("📦 Raw storage_detail response:")
        print(storage_data)  # Print full raw data for inspection

        print("\n🔎 Parsed keys and values:")
        for key, value in storage_data.get("data", {}).items():
            print(f"{key}: {value}")
    except Exception as e:
        print("❌ Failed to get storage_detail.")
        print("Error:", e)

except Exception as e:
    print("❌ Error during login or data fetch.")
    print("Error:", e)

    # Nicely formatted key values
print("\n⚡ Key values:")
print(f"AC Input Voltage    : {storage_data.get('vGrid')} V")
print(f"AC Input Frequency  : {storage_data.get('freqGrid')} Hz")
print(f"AC Output Voltage   : {storage_data.get('outPutVolt')} V")
print(f"AC Output Frequency : {storage_data.get('freqOutPut')} Hz")
print(f"Battery Voltage     : {storage_data.get('vbat')} V")
print(f"Active Power Output : {storage_data.get('activePower')} W")
print(f"Battery Capacity    : {storage_data.get('capacity')}%")
print(f"Load Percentage     : {storage_data.get('loadPercent')}%")
