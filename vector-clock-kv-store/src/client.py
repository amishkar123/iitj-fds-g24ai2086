import requests
import sys

def main():
    nodes = [
        "http://localhost:5000",
        "http://localhost:5001",
        "http://localhost:5002"
    ]
    
    # Test scenario demonstrating causal consistency
    print("Test 1: Basic write to node0")
    requests.post(f"{nodes[0]}/write", json={'key': 'x', 'value': 1})
    
    print("Test 2: Read from node1 with causal dependency")
    response = requests.get(f"{nodes[1]}/read/x")
    if response.status_code == 200:
        value = response.json()['value']
        print(f"Read x={value} from node1")
        requests.post(f"{nodes[1]}/write", json={'key': 'y', 'value': value+1})
    
    print("Test 3: Verify causal consistency at node2")
    response = requests.get(f"{nodes[2]}/read/y")
    if response.status_code == 200:
        print(f"Final y={response.json()['value']} at node2")
    else:
        print("y not found (causal consistency violated)")

if __name__ == '__main__':
    main()