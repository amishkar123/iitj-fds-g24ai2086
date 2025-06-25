from flask import Flask, request, jsonify
from threading import Lock
import requests
import time
import json

app = Flask(__name__)

class VectorClock:
    def __init__(self, node_id, node_count):
        self.node_id = node_id
        self.clock = [0] * node_count
        self.lock = Lock()
    
    def increment(self):
        with self.lock:
            self.clock[self.node_id] += 1
            return self.clock.copy()
    
    def update(self, received_clock):
        with self.lock:
            for i in range(len(self.clock)):
                self.clock[i] = max(self.clock[i], received_clock[i])
    
    def is_causally_ready(self, received_clock):
        # Check if all preceding events have been processed
        for i in range(len(self.clock)):
            if i != self.node_id and received_clock[i] > self.clock[i]:
                return False
        return True

class KVStore:
    def __init__(self, node_id, nodes):
        self.node_id = node_id
        self.nodes = nodes
        self.vector_clock = VectorClock(node_id, len(nodes))
        self.data = {}
        self.buffer = []
        self.lock = Lock()
    
    def local_write(self, key, value):
        clock = self.vector_clock.increment()
        with self.lock:
            self.data[key] = (value, clock)
        self.replicate(key, value, clock)
        return clock
    
    def replicate(self, key, value, clock):
        for i, node_url in enumerate(self.nodes):
            if i != self.node_id:
                try:
                    requests.post(
                        f"{node_url}/replicate",
                        json={
                            'key': key,
                            'value': value,
                            'clock': clock,
                            'sender': self.node_id
                        },
                        timeout=0.5
                    )
                except:
                    pass
    
    def handle_replication(self, key, value, clock, sender):
        with self.lock:
            if self.vector_clock.is_causally_ready(clock):
                self.data[key] = (value, clock)
                self.vector_clock.update(clock)
                self.process_buffered()
                return True
            else:
                self.buffer.append((key, value, clock, sender))
                return False
    
    def process_buffered(self):
        processed = []
        for i, (key, value, clock, sender) in enumerate(self.buffer):
            if self.vector_clock.is_causally_ready(clock):
                self.data[key] = (value, clock)
                self.vector_clock.update(clock)
                processed.append(i)
        self.buffer = [item for i, item in enumerate(self.buffer) if i not in processed]

# Initialize the store
NODE_ID = int(environ.get('NODE_ID', 0))
NODES = json.loads(environ.get('NODES', '["http://node0:5000", "http://node1:5000", "http://node2:5000"]'))
store = KVStore(NODE_ID, NODES)

@app.route('/write', methods=['POST'])
def write():
    data = request.json
    clock = store.local_write(data['key'], data['value'])
    return jsonify({'status': 'success', 'clock': clock})

@app.route('/replicate', methods=['POST'])
def replicate():
    data = request.json
    if store.handle_replication(data['key'], data['value'], data['clock'], data['sender']):
        return jsonify({'status': 'processed'})
    else:
        return jsonify({'status': 'buffered'})

@app.route('/read/<key>', methods=['GET'])
def read(key):
    with store.lock:
        if key in store.data:
            return jsonify({
                'value': store.data[key][0],
                'clock': store.data[key][1]
            })
        return jsonify({'error': 'key not found'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)