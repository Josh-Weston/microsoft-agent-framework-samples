import json
import time

def show_telemetry(b: bytes) -> None:
    payload = json.loads(b)
    with open("telemetry.log", "a") as f:
        f.write(b.decode() + "\n")
    signal = payload["signal"]
    records = payload["records"]
    for record in records:
        print(f"{time.time()}: {signal} - {record}")