"""
IoT Smart-Gateway with MQTT  —  CPAN226 Network Programming
===========================================================
Runs its OWN embedded MQTT broker (amqtt / pure Python).
No external Mosquitto needed.

Terminal 1:  python gateway.py
Terminal 2:  python devices/simulator.py
Browser:     http://localhost:5000
"""

import asyncio, json, threading, time
from collections import defaultdict, deque
from datetime import datetime

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template
from flask_socketio import SocketIO

BROKER_HOST    = "127.0.0.1"
BROKER_PORT    = 1883
TOPIC_ROOT     = "iot/devices"
DASHBOARD_PORT = 5000

THRESHOLDS = {
    "temperature": {"min": -10, "max": 80},
    "humidity":    {"min": 0,   "max": 100},
    "pressure":    {"min": 800, "max": 1200},
    "co2":         {"min": 0,   "max": 5000},
    "motion":      {"min": 0,   "max": 1},
    "voltage":     {"min": 0,   "max": 300},
}

devices          = {}
history          = defaultdict(lambda: deque(maxlen=60))
isolated_devices = set()
alert_log        = deque(maxlen=200)
lock             = threading.Lock()

app = Flask(__name__)
app.config["SECRET_KEY"] = "iot-gateway-2026"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

BROKER_CONFIG = {
    "listeners": {"default": {"type": "tcp", "bind": f"{BROKER_HOST}:{BROKER_PORT}"}},
    "sys_interval": 0,
    "auth": {"allow-anonymous": True},
    "topic-check": {"enabled": False},
}

def start_embedded_broker():
    async def _run():
        from amqtt.broker import Broker
        broker = Broker(BROKER_CONFIG)
        await broker.start()
        print(f"[BROKER] Embedded MQTT broker running on port {BROKER_PORT}")
        while True:
            await asyncio.sleep(3600)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_run())

def check_anomaly(device_id, payload):
    return [
        f"{m}={v} outside [{THRESHOLDS[m]['min']},{THRESHOLDS[m]['max']}]"
        for m, v in payload.items()
        if m in THRESHOLDS and isinstance(v, (int, float))
        and not (THRESHOLDS[m]["min"] <= v <= THRESHOLDS[m]["max"])
    ]

def _snapshot(device_id):
    d = devices.get(device_id, {"id": device_id, "name": device_id,
                                 "type":"?","location":"?","status":"ACTIVE","latest":{}})
    return {**d, "isolated": device_id in isolated_devices}

def _emit_alert(alert):
    alert_log.appendleft(alert)
    socketio.emit("alert", alert)

def isolate_device(device_id, reason):
    with lock:
        if device_id in isolated_devices:
            return
        isolated_devices.add(device_id)
        if device_id in devices:
            devices[device_id]["status"] = "ISOLATED"
        alert = {"ts": datetime.now().isoformat(timespec="seconds"),
                 "device": device_id, "type": "ISOLATION",
                 "message": f"Isolated — {reason}"}
        _emit_alert(alert)
        mqtt_client.publish(f"{TOPIC_ROOT}/{device_id}/command",
                            json.dumps({"command":"isolate","reason":reason}), qos=1, retain=True)
        socketio.emit("device_update", _snapshot(device_id))
        print(f"[GATEWAY] ISOLATED {device_id}: {reason}")

def restore_device(device_id):
    with lock:
        if device_id not in isolated_devices:
            return
        isolated_devices.discard(device_id)
        if device_id in devices:
            devices[device_id]["status"] = "ACTIVE"
        alert = {"ts": datetime.now().isoformat(timespec="seconds"),
                 "device": device_id, "type": "RESTORE",
                 "message": "Device restored to network"}
        _emit_alert(alert)
        mqtt_client.publish(f"{TOPIC_ROOT}/{device_id}/command",
                            json.dumps({"command":"restore"}), qos=1, retain=True)
        socketio.emit("device_update", _snapshot(device_id))
        print(f"[GATEWAY] RESTORED {device_id}")

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Gateway client connected (rc={rc})")
    if rc == 0:
        client.subscribe(f"{TOPIC_ROOT}/#", qos=1)

def on_message(client, userdata, msg):
    parts = msg.topic.split("/")
    if len(parts) < 4:
        return
    device_id, subtopic = parts[2], parts[3]
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return
    if subtopic == "register":
        _register(device_id, payload)
    elif subtopic == "data":
        if device_id not in isolated_devices:
            _ingest(device_id, payload)

def _register(device_id, payload):
    with lock:
        if device_id not in devices:
            devices[device_id] = {
                "id": device_id, "name": payload.get("name", device_id),
                "type": payload.get("type","generic"),
                "location": payload.get("location","unknown"),
                "status": "ACTIVE",
                "last_seen": datetime.now().isoformat(timespec="seconds"),
                "latest": {},
            }
            _emit_alert({"ts": datetime.now().isoformat(timespec="seconds"),
                         "device": device_id, "type": "REGISTER",
                         "message": f"New device: {payload.get('name', device_id)}"})
            print(f"[GATEWAY] Registered {device_id}")
    socketio.emit("device_update", _snapshot(device_id))

def _ingest(device_id, payload):
    ts = datetime.now().isoformat(timespec="seconds")
    with lock:
        if device_id not in devices:
            devices[device_id] = {"id":device_id,"name":device_id,"type":"unknown",
                                   "location":"unknown","status":"ACTIVE","last_seen":ts,"latest":{}}
        devices[device_id]["last_seen"] = ts
        devices[device_id]["latest"]    = payload
        history[device_id].append({"ts": ts, **payload})
    anomalies = check_anomaly(device_id, payload)
    if anomalies:
        isolate_device(device_id, "; ".join(anomalies))
    else:
        socketio.emit("sensor_data", {"device_id": device_id, "ts": ts, "data": payload})
        socketio.emit("device_update", _snapshot(device_id))
    print(f"[DATA] {device_id}: {payload}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"[MQTT] Unexpected disconnect (rc={rc})")

mqtt_client = mqtt.Client(client_id="iot-gateway", protocol=mqtt.MQTTv311,
                           callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
mqtt_client.on_connect    = on_connect
mqtt_client.on_message    = on_message
mqtt_client.on_disconnect = on_disconnect

def connect_gateway_client():
    for i in range(1, 11):
        try:
            mqtt_client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            mqtt_client.loop_start()
            return
        except Exception as e:
            print(f"[GATEWAY] Connect attempt {i}/10 failed: {e} — retrying…")
            time.sleep(1)

@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/api/devices")
def api_devices():
    with lock:
        return jsonify([_snapshot(d) for d in devices])

@app.route("/api/alerts")
def api_alerts():
    return jsonify(list(alert_log))

@app.route("/api/stats")
def api_stats():
    with lock:
        total = len(devices); iso = len(isolated_devices)
    return jsonify({"total_devices":total,"active_devices":total-iso,
                    "isolated_devices":iso,"total_alerts":len(alert_log)})

@app.route("/api/devices/<device_id>/isolate", methods=["POST"])
def api_isolate(device_id):
    isolate_device(device_id, "Manual isolation via dashboard")
    return jsonify({"status":"isolated"})

@app.route("/api/devices/<device_id>/restore", methods=["POST"])
def api_restore(device_id):
    restore_device(device_id)
    return jsonify({"status":"restored"})

@socketio.on("connect")
def on_ws_connect():
    with lock:
        snap = [_snapshot(d) for d in devices]
    socketio.emit("init", {"devices": snap, "alerts": list(alert_log)})

@socketio.on("manual_isolate")
def on_manual_isolate(data):
    isolate_device(data["device_id"], "Manual isolation via dashboard")

@socketio.on("manual_restore")
def on_manual_restore(data):
    restore_device(data["device_id"])

if __name__ == "__main__":
    print("=" * 60)
    print("  IoT Smart-Gateway  |  CPAN226 Network Programming")
    print("  Self-contained — NO external Mosquitto needed!")
    print("=" * 60)

    t = threading.Thread(target=start_embedded_broker, daemon=True, name="mqtt-broker")
    t.start()
    print("[GATEWAY] Waiting 3s for embedded broker to start…")
    time.sleep(3)

    connect_gateway_client()

    print(f"[GATEWAY] Dashboard → http://localhost:{DASHBOARD_PORT}")
    socketio.run(app, host="0.0.0.0", port=DASHBOARD_PORT,
                 debug=False, allow_unsafe_werkzeug=True)