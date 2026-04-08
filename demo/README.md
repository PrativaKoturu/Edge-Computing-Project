## Demo: CPU TD3+LTC vs ESP32 int8 policy (Wokwi)

This folder contains the two demo entrypoints required for the teaching/demo moment:
- **`dashboard.py`**: live terminal dashboard (Rich)
- **`compare_mode.py`**: side-by-side CPU LTC vs int8 edge policy comparison on a fixed sequence

---

## 0) Prereqs

- Docker Desktop (for the control plane + Mosquitto)
- PlatformIO installed (`pio`)
- Wokwi CLI installed and configured
- Python 3.11 recommended

If you’re using the devcontainer, it installs Python deps from `control-plane/requirements.txt`.

---

## 1) Start the control plane (MQTT + trainer + traffic)

From repo root:

```bash
docker compose up --build
```

This starts:
- Mosquitto on `localhost:1883`
- TD3 trainer (`control-plane/control_plane/trainer.py`)
- Bursty traffic generator (`control-plane/control_plane/traffic_generator.py`)

---

## 2) Start the live dashboard

In a new terminal (on the host, not inside the docker network):

```bash
python demo/dashboard.py
```

Environment overrides (optional):

```bash
MQTT_HOST=localhost MQTT_PORT=1883 python demo/dashboard.py
```

---

## 3) Build firmware for both nodes

```bash
cd firmware
pio run -e zone-a
pio run -e zone-b
```

---

## 4) Run two Wokwi simulations

Run **two** Wokwi instances (one per node) using the built artifacts for:
- `zone-a`
- `zone-b`

The firmware connects to:
- WiFi SSID `Wokwi-GUEST`
- MQTT broker at `host.wokwi.internal:1883`

Once running, you should see:
- traffic bursts in docker logs
- requests + telemetry flowing in the dashboard
- policy updates every 200 critic updates

---

## 5) Run the CPU vs Edge comparison (offline, key demo)

This runs 20 synthetic requests through:
- **Policy A**: full LTC actor (float32, CPU)
- **Policy B**: quantized int8 8-weight dot product (ESP32-like)

```bash
python demo/compare_mode.py
```

You’ll get per-request prints showing:
- input state vector (8D)
- CPU actor output
- edge int8 score + mapped cache score
- delta (quantization loss proxy)
- aggregate hit-rate / latency comparison

