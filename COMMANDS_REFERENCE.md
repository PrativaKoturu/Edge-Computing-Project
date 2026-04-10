# Commands Reference: Quick Copy-Paste Guide

All commands needed to run the full system with Wokwi and control plane.

---

## Initial Setup (One Time)

```bash
# Automated setup
./setup_wokwi.sh

# Or manual setup
npm install -g wokwi-cli
pip3 install platformio paho-mqtt rich
cd firmware && pio run -e zone-a && pio run -e zone-b && cd ..
docker pull eclipse-mosquitto python:3.11-slim
```

---

## Running Everything (4 Terminals)

### Terminal 1: Control Plane

```bash
docker compose up --build
```

**Wait for:**
```
trainer    | INFO trainer: Trainer loop started
traffic    | INFO traffic: Traffic generator started
```

---

### Terminal 2: Zone A (Wokwi)

```bash
cd firmware
wokwi-cli --build-type pio --project . zone-a --port 9001
```

**Wait for:**
```
[MQTT] Connected
[MQTT] Subscribed: edge/zone-a/request, edge/zone-a/policy
```

---

### Terminal 3: Zone B (Wokwi)

```bash
cd firmware
wokwi-cli --build-type pio --project . zone-b --port 9002
```

**Wait for:**
```
[MQTT] Connected
[MQTT] Subscribed: edge/zone-b/request, edge/zone-b/policy
```

---

### Terminal 4: Comparison Dashboard

```bash
python3 demo/wokwi_comparison_dashboard.py
```

**Wait for:**
```
WOKWI vs CONTROL PLANE COMPARISON DASHBOARD
```

---

## Monitoring & Debugging

### Watch Trainer Logs

```bash
docker compose logs -f trainer
```

**Watch for:**
- `Replay size=XXX` — zones connected
- `updates=N` — training happening
- `critic_loss` decreasing — learning happening

---

### Monitor MQTT Telemetry

```bash
docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry"
```

**Example output:**
```json
{"node_id":"zone-a","cache_hit":false,"latency_ms":1523,"cache_items":5,...}
{"node_id":"zone-b","cache_hit":true,"latency_ms":45,"cache_items":7,...}
```

---

### Monitor Policy Updates

```bash
docker compose exec mqtt mosquitto_sub -t "edge/+/policy"
```

**Example output:**
```json
{"node_id":"zone-a","int8_weights":[-12,34,-5,...],"float_weights":[...]}
```

---

### Watch Zone A Serial Output

```
Terminal 2 (Zone A already running, just watch the output)
```

**Look for:**
```
[req] stream=cnc-01/vibration ... hit=0 latency=1523ms cache=5
[score] i32=12345 decision=1 s=[10,127,100,0,2,5,50,8]
```

---

## Hardware Benchmark (Optional)

### Quick CPU vs Edge Comparison

```bash
python3 demo/hardware_benchmark.py
```

**Output shows:**
- CPU inference: 0.195 ms
- Edge inference: 0.0007 ms
- Speedup: 276x
- Zone hit rates

---

### Compare Mode (After Trainer Running)

```bash
python3 demo/compare_mode.py
```

**Shows:**
- CPU policy decisions
- Edge policy decisions
- Decision deltas
- Hit rate comparison

---

## Cleanup & Shutdown

### Stop Everything Gracefully

```bash
# Terminal 1 (Trainer)
Ctrl+C

# Terminal 2 (Zone A)
Ctrl+C

# Terminal 3 (Zone B)
Ctrl+C

# Terminal 4 (Dashboard)
Ctrl+C

# Docker
docker compose down
```

---

### Stop Docker Only

```bash
docker compose down
```

---

### Kill Wokwi Instances (if stuck)

```bash
pkill -f wokwi-cli
# or on ports
lsof -i :9001 | awk 'NR!=1 {print $2}' | xargs kill -9
lsof -i :9002 | awk 'NR!=1 {print $2}' | xargs kill -9
```

---

## Quick Diagnostics

### Check Docker is Running

```bash
docker ps
# Should show: mqtt, trainer, traffic containers
```

---

### Check MQTT Broker

```bash
docker compose logs mqtt
```

---

### Check Trainer Status

```bash
docker compose logs trainer | tail -20
```

---

### Verify Zone Connectivity

```bash
# Should return immediately if zones are connected
timeout 5 docker compose exec mqtt mosquitto_pub -t "test" -m "ping"
```

---

### Check Python Dependencies

```bash
python3 -c "import paho.mqtt.client; print('✓ paho-mqtt')"
python3 -c "import rich; print('✓ rich')"
```

---

### Check Firmware Compiled

```bash
ls firmware/.pio/build/zone-a/firmware.bin
ls firmware/.pio/build/zone-b/firmware.bin
```

---

## Environment Variables

### Docker Compose

```bash
# Set trainer device (auto-detect by default)
CUDA_VISIBLE_DEVICES=0 docker compose up

# Set traffic generation speed
BURST_PERIOD_S=15 docker compose up  # Faster bursts
BURST_MIN_KB=300 docker compose up   # Smaller payloads
```

---

### Wokwi Simulation

```bash
# Port configuration
wokwi-cli ... --port 9001  # Zone A
wokwi-cli ... --port 9002  # Zone B

# MQTT host (Wokwi internal)
# (Already configured in platformio.ini: host.wokwi.internal)
```

---

## Performance Tuning

### Faster Training (If GPU Available)

The trainer auto-detects GPU. Make sure:
```bash
# Check CUDA availability
python3 -c "import torch; print(torch.cuda.is_available())"

# Run normally
docker compose up  # Will use GPU if available
```

### Reduce Dashboard Refresh Rate

```bash
# Edit demo/wokwi_comparison_dashboard.py, change:
time.sleep(2)  # → time.sleep(5)  # Update every 5 seconds
```

### Reduce Benchmark Time

```bash
# Edit demo/hardware_benchmark.py, change:
benchmark_cpu_policy(actor, num_runs=1000)  # → num_runs=100
```

---

## Files & Paths

```
Project Root:
├── docker-compose.yml              (MQTT + Trainer)
├── firmware/
│   ├── platformio.ini              (Zone config)
│   ├── src/
│   │   └── main.cpp                (ESP32 code)
│   └── .pio/build/
│       ├── zone-a/firmware.bin     (Compiled)
│       └── zone-b/firmware.bin     (Compiled)
├── control-plane/
│   ├── control_plane/
│   │   ├── trainer.py              (TD3 trainer)
│   │   ├── models.py               (TD3+LTC)
│   │   ├── profiler.py             (Metrics)
│   │   └── state_tracker.py        (Per-zone state)
│   └── requirements.txt
├── demo/
│   ├── wokwi_comparison_dashboard.py  (Real-time UI)
│   ├── hardware_benchmark.py           (Speed test)
│   ├── compare_mode.py                 (CPU vs Edge)
│   └── dashboard.py                    (Trainer stats)
└── docs/
    ├── WOKWI_SETUP.md                  (Detailed setup)
    ├── RUN_FULL_SYSTEM.md              (Step-by-step)
    └── IMPLEMENTATION_SUMMARY.md       (Architecture)
```

---

## Terminal Layout (tmux/screen)

```bash
# Create 4-pane layout
tmux new-session -d -s work -x 200 -y 50

# Pane 1 (top-left): Trainer
tmux send-keys -t work 'docker compose up --build' Enter

# Pane 2 (top-right): Zone A
tmux send-keys -t work 'cd firmware && wokwi-cli --build-type pio --project . zone-a --port 9001' Enter

# Pane 3 (bottom-left): Zone B
tmux send-keys -t work 'cd firmware && wokwi-cli --build-type pio --project . zone-b --port 9002' Enter

# Pane 4 (bottom-right): Dashboard
tmux send-keys -t work 'python3 demo/wokwi_comparison_dashboard.py' Enter

# Attach to session
tmux attach -t work
```

---

## Common Issues Quick Fix

| Issue | Command |
|-------|---------|
| Docker not running | `docker compose up --build` |
| MQTT not accessible | `docker compose down && docker compose up --build` |
| Wokwi port in use | `lsof -i :9001 \| awk 'NR!=1 {print $2}' \| xargs kill -9` |
| Firmware not compiled | `cd firmware && pio run -e zone-a && pio run -e zone-b` |
| Python deps missing | `pip3 install paho-mqtt rich` |
| Dashboard not updating | Check MQTT: `docker compose logs mqtt` |
| No telemetry data | Check zones: `docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry"` |

---

## One-Liner: Full System

```bash
# Start everything (requires 4 terminal windows)
docker compose up --build &
cd firmware && wokwi-cli --build-type pio --project . zone-a --port 9001 &
cd firmware && wokwi-cli --build-type pio --project . zone-b --port 9002 &
sleep 30 && python3 demo/wokwi_comparison_dashboard.py
```

---

**Done! Copy-paste these commands into your terminals.** ✓
