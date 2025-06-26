from flask import Flask, request, jsonify
from threading import Lock
import requests
import json
import time
from os import environ
import logging
from collections import defaultdict

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VectorClock:
    def __init__(self, node_id, node_count):
        self.node_id = node_id
        self.clock = {str(i): 0 for i in range(node_count)}
        self.lock = Lock()
    
    def increment(self):
        with self.lock:
            self.clock[str(self.node_id)] += 1
            return self.clock.copy()
    
    def update(self, received_clock):
        with self.lock:
            for node, time in received_clock.items():
                node_str = str(node)  
                if time > self.clock.get(node_str, 0):
                    self.clock[node_str] = time
    
    def is_causally_ready(self, received_clock):
        for node, time in received_clock.items():
            node_str = str(node)
            if node_str != str(self.node_id) and time > self.clock.get(node_str, 0):
                return False
        return True

class KVStore:
    def __init__(self, node_id, nodes):
        self.node_id = node_id
        self.nodes = nodes
        self.vector_clock = VectorClock(node_id, len(nodes))
        self.data = {}
        self.pending_writes = []
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
                except Exception as e:
                    logger.warning(f"Failed to replicate to node {i}: {e}")
    
    def handle_replication(self, key, value, clock, sender):
        with self.lock:
            if self.vector_clock.is_causally_ready(clock):
                self.data[key] = (value, clock)
                self.vector_clock.update(clock)
                self.process_pending()
                return True
            else:
                self.pending_writes.append((key, value, clock, sender))
                return False
    
    def process_pending(self):
        processed = []
        for i, (key, value, clock, sender) in enumerate(self.pending_writes):
            if self.vector_clock.is_causally_ready(clock):
                self.data[key] = (value, clock)
                self.vector_clock.update(clock)
                processed.append(i)
        self.pending_writes = [w for i, w in enumerate(self.pending_writes) if i not in processed]

def load_config():
    try:
        node_id = int(environ.get('NODE_ID', 0))
        nodes_str = environ.get('NODES', '["http://node0:5000", "http://node1:5000", "http://node2:5000"]')
        nodes = json.loads(nodes_str)
        return node_id, nodes
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        return 0, ["http://node0:5000", "http://node1:5000", "http://node2:5000"]

NODE_ID, NODES = load_config()
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
    return jsonify({'status': 'buffered'})

@app.route('/read/<key>', methods=['GET'])
def read(key):
    with store.lock:
        if key in store.data:
            return jsonify({
                'status': 'success',
                'value': store.data[key][0],
                'clock': store.data[key][1]
            })
        return jsonify({
            'status': 'error',
            'error': 'key not found'
        }), 404

@app.route('/debug', methods=['GET'])
def debug():
    with store.lock:
        # Convert data to serializable format
        serializable_data = {
            key: {
                'value': value[0],
                'clock': {str(k): v for k, v in value[1].items()}  # Ensure string keys
            }
            for key, value in store.data.items()
        }
        
        return jsonify({
            'data': serializable_data,
            'pending_writes': len(store.pending_writes),
            'clock': {str(k): v for k, v in store.vector_clock.clock.items()}  # String keys
        })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)