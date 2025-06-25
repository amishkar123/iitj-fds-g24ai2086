from threading import Thread
from flask import Flask, request, jsonify
from prometheus_client import start_http_server, Gauge, Counter, generate_latest
import random
import time

app = Flask(__name__)
current_load = Gauge('current_load', 'Current load of the substation')
charging_requests = Counter('charging_requests_total', 'Total charging requests')

# Simulate some background load variation
def simulate_load():
    while True:
        current_load.set(max(0, current_load._value.get() + random.uniform(-5, 5)))
        time.sleep(1)

@app.route('/charge', methods=['POST'])
def handle_charge():
    data = request.json
    charging_requests.inc()
    current_load.inc(10)
    # Simulate charging time
    time.sleep(random.uniform(0.1, 0.5))
    return jsonify({
        "status": "charging",
        "substation": request.host,
        "load": current_load._value.get()
    })

@app.route('/metrics')
def metrics():
    return generate_latest()

if __name__ == '__main__':
    start_http_server(6001)
    Thread(target=simulate_load, daemon=True).start()
    app.run(host='0.0.0.0', port=6000)