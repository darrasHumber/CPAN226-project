"""
IoT Device Simulator  |  CPAN226 Network Programming
=====================================================
Simulates 6 IoT devices of 4 different types, each publishing
sensor data to the MQTT broker on its own thread.

Topics published:
  iot/devices/<device_id>/register   — on startup
  iot/devices/<device_id>/data       — every PUBLISH_INTERVAL seconds

One device (env-sensor-3) intentionally generates anomalous readings
after 30 seconds to demonstrate the gateway's auto-isolation feature.
"""

import json
import random
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

# ─── Config ───────────────────────────────────────────────────────────────────

BROKER_HOST      = "localhost"
BROKER_PORT      = 1883
TOPIC_ROOT       = "iot/devices"
PUBLISH_INTERVAL = 3       # seconds between readings
FAULT_DELAY      = 30      # seconds before faulty device starts misbehaving

# ─── Device Definitions ───────────────────────────────────────────────────────

DEVICES = [
    {
        "id": "temp-sensor-1",
        "name": "Temperature Sensor — Lab A",
        "type": "environment",
        "location": "Lab A",
        "metrics": {
            "temperature": (18.0, 26.0),   # (min, max) normal range
            "humidity":    (35.0, 65.0),
        },
    },
    {
        "id": "temp-sensor-2",
        "name": "Temperature Sensor — Lab B",
        "type": "environment",
        "location": "Lab B",
        "metrics": {
            "temperature": (20.0, 28.0),
            "humidity":    (30.0, 70.0),
        },
    },
    {
        "id": "env-sensor-3",
        "name": "CO₂ & Pressure Sensor — Server Room",
        "type": "environment",
        "location": "Server Room",
        "metrics": {
            "temperature": (15.0, 25.0),
            "pressure":    (1000.0, 1015.0),
            "co2":         (400.0, 800.0),
        },
        "faulty": True,     # will generate anomalies after FAULT_DELAY
    },
    {
        "id": "motion-sensor-4",
        "name": "Motion Detector — Entrance",
        "type": "security",
        "location": "Entrance",
        "metrics": {
            "motion": (0, 1),
        },
    },
    {
        "id": "power-monitor-5",
        "name": "Power Monitor — Main Panel",
        "type": "power",
        "location": "Utility Room",
        "metrics": {
            "voltage": (220.0, 240.0),
        },
    },
    {
        "id": "power-monitor-6",
        "name": "Power Monitor — UPS",
        "type": "power",
        "location": "Server Room",
        "metrics": {
            "voltage": (218.0, 242.0),
        },
    },
]

# ─── MQTT Client ──────────────────────────────────────────────────────────────

client = mqtt.Client(client_id="device-simulator", protocol=mqtt.MQTTv311,
                     callback_api_version=mqtt.CallbackAPIVersion.VERSION1)


def connect_broker():
    for attempt in range(1, 6):
        try:
            client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            client.loop_start()
            print(f"[SIM] Connected to broker at {BROKER_HOST}:{BROKER_PORT}")
            return
        except Exception as e:
            print(f"[SIM] Attempt {attempt}/5 failed: {e}. Retrying in 2s…")
            time.sleep(2)
    raise RuntimeError("Could not connect to MQTT broker after 5 attempts.")


# ─── Device Thread ────────────────────────────────────────────────────────────

def device_thread(device: dict):
    dev_id     = device["id"]
    is_faulty  = device.get("faulty", False)
    start_time = time.time()

    # 1. Register
    reg_payload = json.dumps({
        "name":     device["name"],
        "type":     device["type"],
        "location": device["location"],
    })
    client.publish(
        f"{TOPIC_ROOT}/{dev_id}/register",
        reg_payload,
        qos=1,
        retain=True,
    )
    print(f"[SIM] {dev_id} → registered")
    time.sleep(random.uniform(0.1, 1.0))   # stagger startup

    # 2. Publish data loop
    while True:
        elapsed = time.time() - start_time
        data    = {}

        for metric, (lo, hi) in device["metrics"].items():
            if is_faulty and elapsed > FAULT_DELAY:
                # Generate intentionally out-of-range value
                if metric == "co2":
                    val = random.uniform(6000, 9000)    # way above 5000 ppm limit
                elif metric == "temperature":
                    val = random.uniform(85, 120)       # above 80°C limit
                else:
                    val = random.uniform(lo, hi)
            else:
                # Normal Gaussian noise around midpoint
                mid   = (lo + hi) / 2
                sigma = (hi - lo) / 6
                val   = max(lo, min(hi, random.gauss(mid, sigma)))

            # Round nicely: binary stays int, others 2 dp
            if metric == "motion":
                data[metric] = random.choice([0, 1])
            else:
                data[metric] = round(val, 2)

        client.publish(
            f"{TOPIC_ROOT}/{dev_id}/data",
            json.dumps(data),
            qos=0,
        )
        time.sleep(PUBLISH_INTERVAL)

# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  IoT Device Simulator  |  CPAN226 Network Programming")
    print("=" * 60)
    print(f"[SIM] Spawning {len(DEVICES)} device(s)…")
    print(f"[SIM] NOTE: env-sensor-3 will fault after {FAULT_DELAY}s → auto-isolation demo")
    print()

    connect_broker()

    threads = []
    for dev in DEVICES:
        t = threading.Thread(target=device_thread, args=(dev,), daemon=True, name=dev["id"])
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SIM] Shutting down simulator…")
        client.disconnect()