# IoT Smart-Gateway with MQTT
**CPAN226 – Network Programming | Winter 2026**

---

## What This Project Does

A central IoT gateway that:
- Collects sensor data from **6 simulated devices** via MQTT
- Shows a **real-time dashboard** at `http://localhost:5000`
- **Automatically isolates** any device with abnormal readings
- Supports **manual isolate / restore** from the dashboard

> No external software needed — the MQTT broker runs inside Python.

---

## Project Files

```
CPAN226-project/
├── gateway.py           ← Main server (run this first)
├── devices/
│   └── simulator.py     ← Simulates 6 IoT devices (run this second)
├── templates/
│   └── dashboard.html   ← Web dashboard (opens in browser)
└── README.md
```

---

## Setup (One Time)

Install dependencies:
```bash
pip install paho-mqtt flask flask-socketio amqtt
```

---

## How to Run

**Terminal 1 — Start the gateway:**
```bash
python gateway.py
```
Wait until you see:
```
[BROKER] Embedded MQTT broker running on port 1883
[MQTT] Gateway client connected (rc=0)
[GATEWAY] Dashboard → http://localhost:5000
```

**Terminal 2 — Start the device simulator:**
```bash
python devices/simulator.py
```

**Browser:** open `http://localhost:5000`

---

## Simulated Devices

| Device | Type | Metrics |
|--------|------|---------|
| temp-sensor-1 | Environment | temperature, humidity |
| temp-sensor-2 | Environment | temperature, humidity |
| env-sensor-3 | Environment | temperature, pressure, co2 ⚠️ |
| motion-sensor-4 | Security | motion (0/1) |
| power-monitor-5 | Power | voltage |
| power-monitor-6 | Power | voltage |

> ⚠️ `env-sensor-3` intentionally sends bad CO₂ readings after **30 seconds** to trigger auto-isolation — this is the demo feature.

---

## Auto-Isolation Thresholds

| Metric | Normal Range |
|--------|-------------|
| temperature | −10 °C to 80 °C |
| humidity | 0% to 100% |
| pressure | 800 to 1200 hPa |
| co2 | 0 to 5000 ppm |
| voltage | 0 to 300 V |

---

## Architecture

```
simulator.py  →  MQTT Broker (embedded)  →  gateway.py  →  dashboard (browser)
  6 devices       port 1883 / Python          Flask            http://localhost:5000
```

MQTT Topics used:
- `iot/devices/<id>/register` — device announces itself
- `iot/devices/<id>/data` — sensor readings
- `iot/devices/<id>/command` — gateway sends isolate/restore

---

## Evaluation Rubric Alignment

| Criterion | Implementation |
|-----------|---------------|
| Functional Demo (50%) | 6 live devices, real-time dashboard, auto-isolation |
| Network Knowledge (30%) | MQTT pub/sub, QoS levels, retained messages, WebSocket, TCP |
| Technical Significance (20%) | Industry-standard IoT protocol, anomaly detection, event-driven design |