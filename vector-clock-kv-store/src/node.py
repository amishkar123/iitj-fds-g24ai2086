import os
import json
import time
import requests
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

NODE_ID = os.getenv('NODE_ID', 'default_node')
PEER_NODES_STR = os.getenv('PEER_NODES', '')
PEER_NODES = [url.strip() for url in PEER_NODES_STR.split(',') if url.strip()]

kv_store = {} 
kv_lock = threading.Lock() 
vector_clock = {}
vc_lock = threading.Lock()

message_buffer = []
buffer_lock = threading.Lock()

def initialize_vector_clock():
    
    with vc_lock:
        app.logger.info(f"Node {NODE_ID}: Initializing vector clock...")
        vector_clock[NODE_ID] = 0 
        for peer_url in PEER_NODES:
            peer_id = peer_url.split('//')[1].split(':')[0] 
            if peer_id not in vector_clock:
                vector_clock[peer_id] = 0
        app.logger.info(f"Node {NODE_ID}: Vector clock initialized: {vector_clock}")

def get_current_vector_clock():

    with vc_lock:
        current_vc_copy = vector_clock.copy()
        
        all_known_nodes = set(current_vc_copy.keys())
        all_known_nodes.add(NODE_ID) 
        for peer_url in PEER_NODES: 
            all_known_nodes.add(peer_url.split('//')[1].split(':')[0])

        for node_id in all_known_nodes:
            if node_id not in current_vc_copy:
                current_vc_copy[node_id] = 0
        return current_vc_copy

def increment_vector_clock():
    with vc_lock:
        vector_clock[NODE_ID] = vector_clock.get(NODE_ID, 0) + 1
        app.logger.info(f"Node {NODE_ID}: Local event, incremented VC component for self. Current VC: {get_current_vector_clock()}")

def update_vector_clock(received_vc):
    with vc_lock:
        app.logger.info(f"Node {NODE_ID}: Merging received VC {received_vc} into local VC {vector_clock}")
        for node_id, clock_value in received_vc.items():
            vector_clock[node_id] = max(vector_clock.get(node_id, 0), clock_value)
        app.logger.info(f"Node {NODE_ID}: VC after merge: {vector_clock}")

def is_causally_ready(message_vc, current_vc_at_check_time, sender_id):
    app.logger.debug(f"Node {NODE_ID}: Checking causal readiness for msg from {sender_id} (Msg VC: {message_vc}) against my VC: {current_vc_at_check_time}")

    if message_vc.get(sender_id, 0) != current_vc_at_check_time.get(sender_id, 0) + 1:
        app.logger.debug(f"Node {NODE_ID}: Delaying from {sender_id} - sender's clock not exactly +1. My {current_vc_at_check_time.get(sender_id, 0)}, Msg {message_vc.get(sender_id, 0)}")
        return False
    for node_id_in_msg_vc, clock_value_in_msg_vc in message_vc.items():
        if node_id_in_msg_vc != sender_id:
            if current_vc_at_check_time.get(node_id_in_msg_vc, 0) < clock_value_in_msg_vc:
                app.logger.debug(f"Node {NODE_ID}: Delaying from {sender_id} - missing dependency on {node_id_in_msg_vc}. My {current_vc_at_check_time.get(node_id_in_msg_vc, 0)}, Msg {clock_value_in_msg_vc}")
                return False
            
    app.logger.debug(f"Node {NODE_ID}: Message from {sender_id} is causally ready.")
    return True

def process_single_buffered_message(msg_data):
    key = msg_data['key']
    value = msg_data['value']
    sender_id = msg_data['sender_id']
    message_vc = msg_data['vector_clock']

    app.logger.info(f"Node {NODE_ID}: Delivering buffered write from {sender_id}: {key}={value} (Msg VC: {message_vc})")
    
    with kv_lock:
        kv_store[key] = value
    
    
    update_vector_clock(message_vc)
    app.logger.info(f"Node {NODE_ID}: Processed buffered {key}. New VC: {get_current_vector_clock()}")


def process_buffered_messages_thread():

    while True:
        delivered_this_cycle = False
        with buffer_lock:
            if not message_buffer:
                time.sleep(0.05) 
                continue
            remaining_messages = []
            
            current_vc_for_check = get_current_vector_clock() 

            for msg_data in message_buffer:
                msg_vc = msg_data['vector_clock']
                sender_id = msg_data['sender_id']
                
                if is_causally_ready(msg_vc, current_vc_for_check, sender_id):
                    process_single_buffered_message(msg_data)
                    delivered_this_cycle = True
                    current_vc_for_check = get_current_vector_clock()
                else:
                    remaining_messages.append(msg_data)
            
            message_buffer[:] = remaining_messages 

        if not delivered_this_cycle:
           
            time.sleep(0.1)
        

@app.route('/get/<key>', methods=['GET'])
def get_key(key):
    increment_vector_clock()
    with kv_lock:
        value = kv_store.get(key)
    app.logger.info(f"Node {NODE_ID}: GET request for key '{key}'. Value: '{value}'. Current VC: {get_current_vector_clock()}")
    return jsonify({"key": key, "value": value, "vector_clock": get_current_vector_clock()}), 200

@app.route('/put', methods=['POST'])
def put_key():
    data = request.get_json()
    key = data.get('key')
    value = data.get('value')

    if not key or value is None:
        return jsonify({"error": "Key and value are required"}), 400

    increment_vector_clock() 
    current_vc_for_replication = get_current_vector_clock() 

    with kv_lock:
        kv_store[key] = value
    app.logger.info(f"Node {NODE_ID}: PUT request for {key}={value}. Current VC: {current_vc_for_replication}")

    replicate_write(key, value, current_vc_for_replication, NODE_ID)

    return jsonify({"status": "success", "key": key, "value": value, "vector_clock": current_vc_for_replication}), 200

def replicate_write(key, value, current_vc, original_sender_id):
    message_payload = {
        'type': 'replicate_write',
        'key': key,
        'value': value,
        'vector_clock': current_vc, 
        'sender_id': original_sender_id 
    }
    
    app.logger.info(f"Node {NODE_ID}: Initiating replication for {key} to peers with VC {current_vc}")
    for peer_url in PEER_NODES:
        try:
            peer_id = peer_url.split('//')[1].split(':')[0]
            if peer_id == NODE_ID:
                continue 

            requests.post(f"{peer_url}/replicate", json=message_payload, timeout=30)
            app.logger.info(f"Node {NODE_ID}: Sent replication for {key} to {peer_url}")
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Node {NODE_ID}: Failed to replicate {key} to {peer_url}: {e}")

@app.route('/replicate', methods=['POST'])
def receive_replication():
    
    message_data = request.get_json()
    msg_type = message_data.get('type')
    
    if msg_type == 'replicate_write':
        key = message_data['key']
        value = message_data['value']
        message_vc = message_data['vector_clock']
        sender_id = message_data['sender_id'] 

        app.logger.info(f"Node {NODE_ID}: Received replicate_write for '{key}' from {sender_id} (Msg VC: {message_vc}). My current VC: {get_current_vector_clock()}")

        
        current_vc_at_receipt = get_current_vector_clock() 

        if is_causally_ready(message_vc, current_vc_at_receipt, sender_id):
            
            process_single_buffered_message(message_data) 
            app.logger.info(f"Node {NODE_ID}: Processed direct replication for {key}. New VC: {get_current_vector_clock()}")
            return jsonify({"status": "replicated", "key": key}), 200
        else:
            
            with buffer_lock:
                message_buffer.append(message_data)
            app.logger.warning(f"Node {NODE_ID}: Buffered replication for {key} from {sender_id}. Not causally ready. Buffered: {len(message_buffer)} msgs. Current VC: {get_current_vector_clock()}")
            return jsonify({"status": "buffered", "key": key}), 202 
    return jsonify({"error": "Unknown message type"}), 400

@app.route('/status', methods=['GET'])
def get_status():
   
    with kv_lock:
        current_kv = kv_store.copy()
    current_vc_copy = get_current_vector_clock()
    with buffer_lock:
        buffered_count = len(message_buffer)
    return jsonify({"node_id": NODE_ID, "kv_store": current_kv, "vector_clock": current_vc_copy, "buffered_messages_count": buffered_count}), 200

if __name__ == '__main__':
    
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    initialize_vector_clock()
    
    
    buffer_processor_thread = threading.Thread(target=process_buffered_messages_thread)
    buffer_processor_thread.daemon = True 
    buffer_processor_thread.start()
    
    app.run(host='0.0.0.0', port=5000, debug=False)

