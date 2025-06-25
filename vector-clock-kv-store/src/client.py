import requests
import time
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

NODE_URLS = {
    'node1': "http://localhost:5001",
    'node2': "http://localhost:5002",
    'node3': "http://localhost:5003"
}


def get_node_status(node_name):
    url = f"{NODE_URLS[node_name]}/status"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to get status from {node_name} ({url}): {e}")
        return None

def put_key(node_name, key, value):
    url = f"{NODE_URLS[node_name]}/put"
    payload = {"key": key, "value": value}
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        logging.info(f"PUT '{key}':'{value}' on {node_name}. Response: {result}")
        return result
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to PUT '{key}' on {node_name} ({url}): {e}")
        return None

def get_key(node_name, key):
    url = f"{NODE_URLS[node_name]}/get/{key}"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        result = response.json()
        logging.info(f"GET '{key}' from {node_name}. Response: {result}")
        return result
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to GET '{key}' from {node_name} ({url}): {e}")
        return None

def verify_causal_consistency():
    logging.info("Checking initial node status...")
    for node_name in NODE_URLS.keys():
        status = get_node_status(node_name)
        if status:
            logging.info(f"{node_name} initial status: KV: {status['kv_store']}, VC: {status['vector_clock']}, Buffered: {status['buffered_messages_count']}")
        else:
            logging.error(f"Node {node_name} not reachable at {NODE_URLS[node_name]}. Please ensure Docker Compose is up and running.")
            sys.exit(1)
    time.sleep(2)

    logging.info("\n--- EVENT 1: Writing 'msg_1' on node1 ---")
    put_result_1 = put_key('node1', 'msg_1', 'Hello from Node1!')
    if not put_result_1:
        return False
    time.sleep(0.5)
    logging.info("\n--- EVENT 2: Writing 'msg_2' on node2 ---")
    put_result_2 = put_key('node2', 'msg_2', 'Hello from Node2!')
    if not put_result_2:
        return False
    time.sleep(0.5)

    logging.info("\n--- EVENT 3: Writing 'msg_3' on node3 ---")
    put_result_3 = put_key('node3', 'msg_3', 'Hello from Node3!')
    if not put_result_3:
        return False
    time.sleep(0.5)

    
    logging.info("\n--- Verifying final state on all nodes ---")
    all_consistent = True
    expected_keys = {'msg_1', 'msg_2', 'msg_3'}
    
    for node_name in NODE_URLS.keys():
        status = get_node_status(node_name)
        if status:
            current_kv = status['kv_store']
            current_vc = status['vector_clock']
            buffered_count = status['buffered_messages_count']
            
            logging.info(f"\n{node_name} FINAL STATE:")
            logging.info(f"  KV Store: {current_kv}")
            logging.info(f"  Vector Clock: {current_vc}")
            logging.info(f"  Buffered Messages: {buffered_count}")

            if all(key in current_kv for key in expected_keys):
                logging.info(f"  --> {node_name} has all expected data.")
            else:
                logging.warning(f"  --> {node_name} is MISSING some data: {expected_keys.difference(current_kv.keys())}")
                all_consistent = False
            
            if buffered_count != 0:
                logging.error(f"  --> {node_name} still has buffered messages! This indicates a causal dependency was not met or a bug.")
                all_consistent = False
        else:
            all_consistent = False

    if all_consistent:
        logging.info("\n--- End of Verification Scenario ---")
        logging.info("Basic data consistency check PASSED.")
    else:
        logging.error("\n--- End of Verification Scenario ---")
        logging.error("Consistency check FAILED. Some nodes did not replicate all data correctly.")
    return all_consistent

if __name__ == "__main__":
    verify_causal_consistency()
