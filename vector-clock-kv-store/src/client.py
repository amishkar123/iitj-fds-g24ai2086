import requests
import time
import sys

def wait_for_service(url, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{url}/debug", timeout=1)
            if response.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False

def test_causal_consistency(nodes):
    print("\n=== Test 1: Writing initial value to node0 ===")
    try:
        response = requests.post(
            f"{nodes[0]}/write",
            json={'key': 'x', 'value': 1},
            timeout=2
        )
        response.raise_for_status()
        print(f"Write successful. Clock: {response.json()['clock']}")
    except Exception as e:
        print(f"Failed to write to node0: {e}")
        return False

    print("\n=== Test 2: Reading from node1 and writing dependent value ===")
    try:
        response = requests.get(f"{nodes[1]}/read/x", timeout=2)
        response.raise_for_status()
        data = response.json()
        print(f"Read response: {data}")
        
        if 'value' not in data:
            print("Error: 'value' not found in response")
            print(f"Full response: {data}")
            return False
            
        new_val = data['value'] + 1
        print(f"Updating value from {data['value']} to {new_val}")
        
        response = requests.post(
            f"{nodes[1]}/write",
            json={'key': 'y', 'value': new_val},
            timeout=2
        )
        response.raise_for_status()
        print(f"Write successful. Clock: {response.json()['clock']}")
    except Exception as e:
        print(f"Failed during dependent write: {e}")
        return False

    print("\n=== Test 3: Verifying at node2 ===")
    try:
        response = requests.get(f"{nodes[2]}/read/y", timeout=2)
        if response.status_code == 200:
            data = response.json()
            print(f"Causal consistency verified: y={data['value']}")
            print(f"Vector clock: {data['clock']}")
            return True
        else:
            print(f"Causal consistency violation! Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"Verification failed: {e}")
        return False

def print_debug_info(nodes):
    print("\n=== System State ===")
    for i, node in enumerate(nodes):
        try:
            debug = requests.get(f"{node}/debug", timeout=1).json()
            print(f"\nNode {i} ({node}):")
            print("Data:", debug.get('data'))
            print("Pending writes:", debug.get('pending_writes'))
            print("Vector clock:", debug.get('clock'))
        except:
            print(f"Could not get debug info from node {i}")

def main():
    nodes = ["http://node0:5000", "http://node1:5000", "http://node2:5000"]

    print("Waiting for nodes to be ready...")
    for i, node in enumerate(nodes):
        if not wait_for_service(node):
            print(f"Node {i} ({node}) not ready after timeout")
            print_debug_info(nodes)
            return
    
    success = test_causal_consistency(nodes)
    
    print_debug_info(nodes)
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()