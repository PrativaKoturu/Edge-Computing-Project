# Edge Computing MARL System

A multi-agent reinforcement learning system that teaches an ESP32 edge node to make smart caching decisions in real time.

The demo shows the contrast between:
- **Full TD3 + LTC policy** running on your CPU/GPU (centralized trainer)
- **Quantized int8 8-weight policy** running on a simulated ESP32 in Wokwi (decentralized edge)

Both sides communicate over MQTT using the same message flow.

---

## What This System Does

A factory floor has 50 CNC machines generating sensor streams (vibration, temperature, pressure). An ESP32 edge node decides which streams to cache locally vs. fetch from cloud. Caching is fast (45 ms); cloud fetch is slow (800–2000 ms).

The RL trainer (on your machine) watches what the edge node does, computes rewards, and trains a neural network (TD3 + LTC). Every 200 updates it compresses the network into 8 int8 weights and pushes them to the ESP32. The ESP32 uses those weights to make smarter caching decisions.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Your Machine (CPU / GPU)                                   │
│                                                             │
│  Traffic Generator  →  MQTT broker (HiveMQ)                │
│                                ↓                           │
│  TD3 Trainer  ←  edge/zone-a/telemetry                      │
│  TD3 Trainer  →  edge/zone-a/policy  (int8 weights)         │
└─────────────────────────────────────────────────────────────┘
                         MQTT (HiveMQ public)
                              ↕
┌─────────────────────────────┐
│  Wokwi (browser)            │
│  ESP32 Simulator            │
│  • 64-item LRU cache        │
│  • int8 dot product policy  │
│  • ~0.7 µs per decision     │
└─────────────────────────────┘
```

**CTDE — Centralized Training, Decentralized Execution:**
- The edge node runs cheap int8 inference (dot product, ~0.7 µs)
- The trainer runs the full TD3+LTC network on CPU/GPU
- The trainer learns from edge telemetry and pushes compressed weights back

---

## Data Flow (step by step)

```
1. Traffic generator sends JSON request  →  edge/zone-a/request
   {"stream_id": "cnc-01/vibration", "payload_kb": 1200, "anomaly": false}

2. ESP32 receives request, builds 8-element state vector:
   [cache_occupancy, latency_norm, payload_norm, anomaly,
    recent_hit_rate, stream_frequency, time_since_last_req, cache_pressure]

3. ESP32 runs int8 dot product:
   score = Σ weight[i] * state[i]   (8 multiplies, ~0.7 µs)
   decision = (score > 0) OR anomaly

4. ESP32 sends telemetry  →  edge/zone-a/telemetry
   {"cache_hit": false, "latency_ms": 1523, "score_int32": -234, ...}

5. Trainer receives telemetry, computes reward:
   reward = +1 (hit) or -1 (miss) - 0.001×latency + 0.5×anomaly×hit - 0.3×pressure

6. Trainer stores (state, action, reward, next_state) in replay buffer.
   Once buffer has 64 transitions, TD3 training begins:
   - Critic update:  minimize MSE between predicted Q and target Q
   - Actor update:   maximize Q value w.r.t. policy
   - Target networks soft-updated every 2 critic steps

7. Every 200 critic updates, trainer quantizes actor weights:
   - SVD of first layer weight matrix W [19×8]
   - Compressed to 8 float values → scaled to int8
   - Published  →  edge/zone-a/policy

8. ESP32 receives new int8 weights, swaps them in immediately.
   Next decisions use the trained policy.
```

**Where is RL happening?**
- **RL inference** (using the policy): on the ESP32, step 3 above
- **RL training** (improving the policy): on your CPU/GPU, step 6 above

---

## Performance

| Where | Policy | Per-inference |
|-------|--------|--------------|
| Your CPU | Full TD3 + LTC neural net | ~0.19 ms |
| Your GPU | Full TD3 + LTC neural net | ~0.02 ms |
| ESP32 (Wokwi) | int8 8-weight dot product | **~0.7 µs** |

Edge is **~270× faster** than CPU. This is why we cannot run the full network on an ESP32.

---

## Running the System

### Prerequisites

- Docker Desktop (running)
- Python 3.11+
- A browser (for Wokwi)

Install Python dependencies:

```bash
cd control-plane
pip install -r requirements.txt
```

---

### Step 1 — Start the control plane (Docker)

```bash
docker compose up --build
```

This starts two containers:

| Container | What it does |
|-----------|-------------|
| `trainer` | TD3 training loop — reads telemetry, updates policy, pushes weights |
| `traffic` | Bursty traffic generator — 50 CNC machines, bursts every 30s |

Both connect to `broker.hivemq.com` (free public MQTT broker).

Wait for:
```
trainer    | INFO trainer: Trainer loop started. Nodes=zone-a
traffic    | INFO traffic: Traffic generator started. period=30.0s
```

---

### Step 2 — Start the ESP32 edge node (Wokwi)

1. Go to **https://wokwi.com/**
2. Click **Start new project** → select **ESP32** → click **Create**
3. Delete all code in the editor
4. Open [firmware/src/main.cpp](firmware/src/main.cpp), copy everything, paste into Wokwi
5. Click **▶ Run**

Watch the serial monitor at the bottom:
```
Boot node_id=zone-a
Connecting WiFi SSID=Wokwi-GUEST
WiFi connected ip=10.10.0.2
Connecting MQTT broker.hivemq.com:1883
MQTT connected. Subscribed: edge/zone-a/request, edge/zone-a/policy
```

Once connected, requests arrive every 30 seconds:
```
[req] stream=cnc-01/vibration payload=1200KB anomaly=0 hit=0 latency=1523ms cache=5
[score] i32=-234 decision=0 s=[10,127,100,0,2,5,50,8]
```

After ~200 critic updates (~2 minutes), the first policy arrives:
```
[policy] updated int8[0]=-12 float_avg=0.123
```

---

### Step 3 — Watch the trainer learn

```bash
docker compose logs -f trainer
```

```
INFO trainer: Replay size=100 latest node=zone-a hit=False lat=1523ms
INFO trainer: updates=50  replay=120  critic_loss(avg10)=0.3421  actor_loss(avg10)=-0.0123
INFO trainer: updates=200 replay=200  critic_loss(avg10)=0.1234  actor_loss(avg10)=-0.0089
```

`critic_loss` decreasing = the model is learning.

---

### Step 4 — Run the hardware benchmark

In a new terminal (with Docker still running):

```bash
python3 demo/hardware_benchmark.py
```

Output:
```
CPU TD3+LTC:              0.195 ms per inference
Edge int8 (simulated):   0.0007 ms per inference  (0.70 µs)
Edge Speedup:             ~270x faster than CPU
```

This is the core comparison — the full neural net on CPU vs. quantized int8 on the ESP32.

---

### Step 5 — Run the live dashboard

```bash
python3 demo/wokwi_comparison_dashboard.py
```

Shows edge node and trainer metrics side by side, refreshing every 2 seconds. The system status panel shows which of the 4 pipeline stages are active.

---

## Showing the Demo to Your Professor

Have these open simultaneously:

| Window | Command | Shows |
|--------|---------|-------|
| Terminal 1 | `docker compose up --build` | Trainer + traffic running |
| Terminal 2 | `docker compose logs -f trainer` | TD3 loss decreasing in real time |
| Terminal 3 | `python3 demo/hardware_benchmark.py` | 270x speedup proof |
| Terminal 4 | `python3 demo/wokwi_comparison_dashboard.py` | Live dashboard |
| Browser | wokwi.com | ESP32 serial: requests + scores + policy updates |

**What to point to:**

1. **Wokwi serial** → "This is the actual RL policy running on an ESP32 at 0.7 µs"
2. **Trainer logs** → "This is the full neural network training on CPU — critic loss going down = it's learning"
3. **Benchmark output** → "270x speedup — full network is too slow for an ESP32, so we quantize"
4. **Dashboard step 4** → "When this says policy pushed, the ESP32 just received new weights from the trained network"

---

## Project Structure

```
.
├── control-plane/
│   ├── control_plane/
│   │   ├── trainer.py            # TD3 loop, GPU detection, policy quantize + publish
│   │   ├── models.py             # LTC actor + TD3 twin critics
│   │   ├── state_tracker.py      # Rolling state windows per node
│   │   ├── replay_buffer.py      # Shared replay buffer
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
│   └── platformio.ini            # Build config
├── demo/
│   ├── hardware_benchmark.py     # CPU vs GPU vs Edge inference speed
│   ├── compare_mode.py           # CPU policy vs Edge policy, side by side
│   ├── wokwi_comparison_dashboard.py  # Live metrics dashboard
│   └── dashboard.py              # Trainer-only stats
├── docker-compose.yml
└── README.md
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Wokwi serial stuck at `Connecting WiFi` | Click Stop then Run again |
| Wokwi shows `MQTT failed rc=-2` | MQTT_HOST in firmware must be `broker.hivemq.com`, not `host.wokwi.internal` |
| Wokwi shows `MQTT failed rc=4` | Docker not running — start `docker compose up --build` first |
| `Replay size=0` stays at 0 | Wokwi not connected — check serial shows `MQTT connected` |
| No `[req]` in Wokwi | Bursts every 30s — wait up to 30s after connecting |
| No policy update after 2 min | Check `docker compose logs trainer` for `updates=200` |
| `ModuleNotFoundError: ncps` | `cd control-plane && pip install -r requirements.txt` |
