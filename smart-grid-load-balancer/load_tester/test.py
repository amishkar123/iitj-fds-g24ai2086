import requests
import threading
import random
import time

CHARGE_SERVICE_URL = "http://charge_request_service:5000/request_charge"

def simulate_ev():
        try:
            print(f"Sending request at {time.ctime()}", flush=True)
            requests.post(CHARGE_SERVICE_URL, json={
                "vehicle_id": f"EV-{random.randint(1000, 9999)}",
                "charge_kwh": random.uniform(10, 50)
            })
        except Exception as e:
            print(f"Request failed: {e}")
        time.sleep(random.uniform(0.1, 1))

def rush_hour_test(duration=2):
    threads = []
    for _ in range(60):
        t = threading.Thread(target=simulate_ev)
        t.start()
        threads.append(t)
        time.sleep(duration)
    for t in threads:
        t.join()

if __name__ == '__main__':
    rush_hour_test()