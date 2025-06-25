from flask import Flask, request, jsonify
import requests

app = Flask(__name__)
LOAD_BALANCER_URL = "http://load_balancer:5001/route"

@app.route('/request_charge', methods=['POST'])
def handle_charge_request():
    data = request.json
    response = requests.post(LOAD_BALANCER_URL, json=data)
    return jsonify(response.json())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)