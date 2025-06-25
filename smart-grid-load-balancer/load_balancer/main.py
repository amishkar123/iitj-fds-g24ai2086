from flask import Flask, request, jsonify
import requests
import time
from threading import Thread
from prometheus_client import start_http_server, Gauge

app = Flask(__name__)
SUBSTATIONS = ["substation1:6000", "substation2:6000", "substation3:6000"]
UPDATE_INTERVAL = 5 

substation_loads = {sub: 0 for sub in SUBSTATIONS}
load_gauge = Gauge('substation_load', 'Current load of substations', ['substation'])

def update_substation_loads():
    while True:
        for sub in SUBSTATIONS:
            try:
                response = requests.get(f"http://{sub}/metrics")
                for line in response.text.split('\n'):
                    if 'current_load' in line and not line.startswith('#'):
                        load = float(line.split(' ')[1])
                        substation_loads[sub] = load
                        load_gauge.labels(substation=sub).set(load)
            except Exception as e:
                print(f"Error updating load for {sub}: {e}")
        time.sleep(UPDATE_INTERVAL)

@app.route('/route', methods=['POST'])
def route_request():
    data = request.json
    least_loaded = min(substation_loads.items(), key=lambda x: x[1])[0]
    print("least loaded",least_loaded)
    try:
        response = requests.post(f"http://{least_loaded}/charge", json=data)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    Thread(target=update_substation_loads, daemon=True).start()
    start_http_server(5002)
    app.run(host='0.0.0.0', port=5001)