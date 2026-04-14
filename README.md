# Edge Computing MARL System

A multi-agent reinforcement learning system that teaches ESP32 edge nodes to make smart caching decisions in real time.

The demo shows the contrast between:
- **Full TD3 + LTC policy** running on your CPU/GPU (centralized trainer)
- **Quantized int8 8-weight policy** running on simulated ESP32 nodes in Wokwi (decentralized edge)

Both sides communicate over MQTT using the same message flow.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Your Machine  (CPU / GPU)                                  │
│  TD3 Trainer + Shared Replay Buffer                         │
│  Learns from both zones → quantizes → pushes int8 policy    │
└──────────────┬──────────────────────┬──────────────────────┘
               │  MQTT                │  MQTT
        ┌──────▼──────┐        ┌──────▼──────┐
        │  Zone A     │        │  Zone B     │
        │  ESP32 Sim  │        │  ESP32 Sim  │
        │  (Wokwi)    │        │  (Wokwi)    │
        └─────────────┘        └─────────────┘
        64-item LRU cache      64-item LRU cache
        int8 dot product       int8 dot product
        ~0.7 µs per decision   ~0.7 µs per decision
```

**CTDE — Centralized Training, Decentralized Execution**

- Zone A and Zone B keep **independent** caches and rolling state windows
- Both send telemetry to the trainer over MQTT
- Trainer learns **one policy** from both zones' experience
- Trainer quantizes and pushes int8 weights back to both zones every 200 updates

---

## Performance Numbers

| Where | Policy | Inference Time |
|-------|--------|---------------|
| Your CPU | Full TD3 + LTC neural net | ~0.19 ms |
| Your GPU | Full TD3 + LTC neural net | ~0.02 ms |
| ESP32 (Wokwi) | int8 8-weight dot product | **~0.7 µs** |

Edge is **276× faster** than CPU — this is why we can't run the full network on an ESP32.

---

---

## Path 1 — Running on CPU / GPU

This is everything that runs on your machine: the MQTT broker, the TD3 trainer, and the traffic generator.

### Prerequisites

- Docker Desktop
- Python 3.11+
- Dependencies:
  ```bash
  cd control-plane
  pip install -r requirements.txt
  ```

### Step 1 — Start the control plane

```bash
docker compose up --build
```

This starts three containers:

| Container | What it does |
|-----------|-------------|
| `mqtt` | Eclipse Mosquitto broker on port 1883 |
| `trainer` | TD3 training loop, reads telemetry, writes policy |
| `traffic` | Bursty traffic generator — 50 CNC machines, 30s bursts |

Wait until you see:
```
trainer    | INFO trainer: Trainer loop started. Nodes=zone-a,zone-b
traffic    | INFO traffic: Traffic generator started. period=30.0s
```

### Step 2 — Watch the trainer learn

Open a second terminal:

```bash
docker compose logs -f trainer
```

You will see:
```
INFO trainer: Replay size=100 latest node=zone-a hit=False lat=1523ms
INFO trainer: updates=50  replay=120  critic_loss(avg10)=0.3421  actor_loss(avg10)=-0.0123
INFO trainer: updates=100 replay=150  critic_loss(avg10)=0.1234  actor_loss(avg10)=-0.0089
```

`critic_loss` decreasing = the model is learning.

### Step 3 — Run the hardware benchmark (CPU vs Edge comparison)

```bash
python3 demo/hardware_benchmark.py
```

Output:
```
CPU TD3+LTC:           0.195 ms per inference
Edge int8 (simulated): 0.0007 ms per inference  (0.70 µs)
Edge Speedup:          276x faster than CPU

Zone A hit rate: 9.0%
Zone B hit rate: 12.0%
```

This is the core proof: full neural net on CPU vs quantized int8 on edge.

### Step 4 — Run the comparison dashboard

```bash
python3 demo/wokwi_comparison_dashboard.py
```

Shows Zone A, Zone B, and trainer metrics side by side, refreshing every 2 seconds.

### Step 5 — Run CPU vs Edge policy comparison

```bash
python3 demo/compare_mode.py
```

Runs 20 synthetic requests through both the full LTC network and the int8 policy. Shows per-request decisions, hit rates, and latency comparison.

---

---

## Path 2 — Running on Wokwi (ESP32 Simulation)

This runs the edge firmware on two simulated ESP32s in the Wokwi web IDE. Each simulator connects to the MQTT broker on your machine and behaves as a real edge node.

**The control plane (Path 1, Step 1) must be running before you start this.**

### Step 1 — Build the firmware

```bash
cd firmware
pio run -e zone-a
pio run -e zone-b
```

This compiles two binaries — one with `NODE_ID="zone-a"` and one with `NODE_ID="zone-b"`.

### Step 2 — Open Wokwi in two browser tabs

Go to **https://wokwi.com/** and open it in **two separate tabs**.

### Step 3 — Set up Tab 1 as Zone A

1. Click **Start new project**
2. Select **ESP32**
3. Click **Create**
4. Delete all code in the editor
5. Open `firmware/src/main.cpp` in your editor, copy everything, paste it into Wokwi
6. Click **▶ Run** (green play button at the top)

Watch the serial monitor at the bottom:
```
[Boot] zone-a
[WiFi] Connecting SSID=Wokwi-GUEST
[WiFi] Connected  ip=10.10.0.2
[MQTT] Connecting mqtt host.wokwi.internal:1883
[MQTT] Connected. Subscribed: edge/zone-a/request, edge/zone-a/policy
```

Zone A is now live and waiting for requests.

### Step 4 — Set up Tab 2 as Zone B

Repeat Step 3 in the second tab, but before clicking Run, find this line in the code:

```cpp
#ifndef NODE_ID
#define NODE_ID "zone-a"    // <-- change this to "zone-b"
#endif
```

Change it to:
```cpp
#define NODE_ID "zone-b"
```

Then click **▶ Run**.

Serial output should show:
```
[Boot] zone-b
[MQTT] Connected. Subscribed: edge/zone-b/request, edge/zone-b/policy
```

### Step 5 — Watch requests come in

Once traffic starts (every 30 seconds), both tabs will show:

```
[req] stream=cnc-01/vibration payload=1200KB anomaly=0 hit=0 latency=1523ms cache=5
[score] i32=12345 decision=1 s=[10,127,100,0,2,5,50,8]
```

- `hit=0` → cache miss, fetch from cloud (800–2000 ms)
- `hit=1` → cache hit, served locally (45 ms)
- `score` → output of the int8 dot product: `Σ w[i] * state[i]`
- `decision=1` → cache this stream for next time

### Step 6 — Watch policy updates arrive

After ~200 critic updates on the trainer side (~2 minutes), both tabs receive new int8 weights:

```
[policy] updated int8[0]=-12 float_avg=0.123
```

The edge node swaps in the new weights immediately. Future decisions use the trained policy.

### What the int8 inference looks like in the firmware

```cpp
// 8-element dot product, runs in ~0.7 µs on ESP32
int32_t score = 0;
for (int i = 0; i < 8; i++) {
    score += (int32_t)policyWeightsInt8[i] * (int32_t)state[i];
}
bool cacheDecision = (score > threshold) || anomaly;
```

This is the entire "neural network" that runs on the ESP32. The full LTC network on CPU takes 0.19 ms and has thousands of operations — the int8 version takes 0.7 µs and has 8 multiplies.

---

---

## Seeing Both Running at the Same Time

The best way to show the comparison is to have all of these open simultaneously:

| Window | Command | Shows |
|--------|---------|-------|
| Terminal 1 | `docker compose up --build` | Trainer + MQTT running |
| Terminal 2 | `docker compose logs -f trainer` | Loss decreasing |
| Terminal 3 | `python3 demo/wokwi_comparison_dashboard.py` | Live metrics |
| Browser Tab 1 | wokwi.com — Zone A | ESP32 serial: requests + scores |
| Browser Tab 2 | wokwi.com — Zone B | ESP32 serial: requests + scores |

Expected timeline once everything is connected:

```
0–10s    Zones boot and connect to MQTT
10–20s   Traffic generator sends first burst, both Wokwi tabs show [req] messages
20–60s   Trainer accumulates telemetry, starts critic updates
~120s    First policy pushed to both zones — [policy] updated in serial output
2+ min   Cache hit rates climb from 0% toward 10–12%
```

---

## Verifying the Connection

```bash
# Confirm containers are running
docker compose ps

# Watch raw telemetry from both zones
docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry"

# Watch policy being sent to zones
docker compose exec mqtt mosquitto_sub -t "edge/+/policy"
```

If the Wokwi serial shows `[MQTT] Connected` and the telemetry subscription shows JSON, everything is wired up correctly.

---

## Project Structure

```
.
├── control-plane/
│   ├── control_plane/
│   │   ├── trainer.py            # TD3 loop, per-zone metrics, GPU detection
│   │   ├── models.py             # LTC actor + TD3 twin critics
│   │   ├── state_tracker.py      # Per-zone independent rolling state
│   │   ├── replay_buffer.py      # Shared global replay buffer
│   │   ├── traffic_generator.py  # 50-machine CNC bursty traffic
│   │   ├── profiler.py           # CPU/memory/timing metrics
│   │   ├── messages.py           # MQTT message schemas
│   │   ├── topics.py             # Topic name helpers
│   │   ├── mqtt_client.py        # MQTT bus wrapper
│   │   └── config.py             # Env var settings
│   ├── Dockerfile
│   └── requirements.txt
├── firmware/
│   ├── src/main.cpp              # ESP32: int8 policy, LRU cache, MQTT
│   └── platformio.ini            # zone-a and zone-b build envs
├── demo/
│   ├── hardware_benchmark.py     # CPU vs GPU vs Edge inference speed
│   ├── compare_mode.py           # CPU policy vs Edge policy, side by side
│   ├── wokwi_comparison_dashboard.py  # Live zone + trainer metrics
│   └── dashboard.py              # Trainer-only stats
├── docker-compose.yml
└── README.md
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Wokwi serial stuck at `Connecting WiFi` | Click Stop then Run again in Wokwi |
| Wokwi shows `[MQTT] failed rc=4` | Docker not running — run `docker compose up --build` first |
| `Replay size=0` stays at 0 | Wokwi not connected — check serial shows `[MQTT] Connected` |
| No `[req]` messages in Wokwi | Traffic bursts every 30s — wait up to 30s after connecting |
| No policy updates after 2 min | Check `docker compose logs trainer` for `updates=200` |
| `ModuleNotFoundError: ncps` | `cd control-plane && pip install -r requirements.txt` |
