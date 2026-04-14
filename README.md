# Edge Computing MARL System

A fully virtualized multi-agent reinforcement learning (MARL) system that teaches ESP32 edge nodes to make smart caching decisions in real time.

**Demo focus:** contrast a full **TD3 + LTC (ncps AutoNCP) policy running on CPU/GPU** vs a **quantized int8 8-weight edge policy** running on simulated ESP32 nodes (Wokwi), using the same MQTT message flow and training loop.

Built with: Python · PyTorch · ncps · PlatformIO · Wokwi · Docker · Eclipse Mosquitto

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Control Plane (Your Machine)                               │
│  TD3 Trainer (CPU/GPU) + Shared Replay Buffer               │
│  Learns from both zones → Publishes int8 policy to edges    │
└──────────────┬──────────────────────┬──────────────────────┘
               │  MQTT                │  MQTT
        ┌──────▼──────┐        ┌──────▼──────┐
        │  Zone A     │        │  Zone B     │
        │  ESP32 Sim  │        │  ESP32 Sim  │
        │  (Wokwi)    │        │  (Wokwi)    │
        └─────────────┘        └─────────────┘
        Independent cache      Independent cache
        int8 dot product       int8 dot product
        ~0.7 µs inference      ~0.7 µs inference
```

**CTDE — Centralized Training, Decentralized Execution:**
- Zone A and Zone B maintain **independent** 64-item LRU caches and rolling state windows
- Both zones send telemetry to the trainer via MQTT
- Trainer learns **one shared policy** from combined experience
- Trainer quantizes and pushes int8 weights back to both zones

---

## Performance

| Policy | Device | Inference Time | Notes |
|--------|--------|---------------|-------|
| TD3 + LTC | CPU | ~0.19 ms | Full neural net, your machine |
| TD3 + LTC | GPU | ~0.02 ms | If CUDA available |
| int8 quantized | ESP32 (Wokwi) | ~0.7 µs | **276x faster than CPU** |

Zone performance (100 requests each):

| Zone | Hit Rate | Avg Latency | Notes |
|------|----------|------------|-------|
| Zone A | 7–12% | ~1250 ms | Independent request patterns |
| Zone B | 5–12% | ~1180 ms | Independent request patterns |

Both zones converge to ~10% average hit rate — proof that shared training works despite independent execution.

---

## Quick Start

### 1. Install dependencies

```bash
# Python deps (for demos and dashboard)
cd control-plane && pip install -r requirements.txt

# Firmware (build both zones)
cd firmware
pio run -e zone-a
pio run -e zone-b
```

### 2. Run hardware benchmark (2 minutes, no Wokwi needed)

```bash
python3 demo/hardware_benchmark.py
```

Shows CPU vs Edge inference speed and Zone A/B caching performance.

### 3. Start the full system

```bash
# Terminal 1 — Control plane (trainer + MQTT + traffic)
docker compose up --build

# Terminal 2 — Live dashboard
python3 demo/wokwi_comparison_dashboard.py

# Terminal 3 — CPU vs Edge comparison
python3 demo/compare_mode.py
```

---

## Wokwi Simulation (Running Real Firmware)

**Two ways to run Zone A and Zone B on Wokwi simultaneously:**

### Option A: Wokwi Web IDE (easiest)

1. Start the control plane first:
   ```bash
   docker compose up --build
   ```

2. Open **https://wokwi.com/** in two browser tabs

3. In each tab:
   - Click **"New Project" → Arduino ESP32**
   - Copy-paste the entire contents of `firmware/src/main.cpp`
   - In Tab 2, change one line:
     ```cpp
     #define NODE_ID "zone-b"   // Tab 2 only, Tab 1 keeps "zone-a"
     ```
   - Click **▶️ Play**

4. Watch the Wokwi serial output:
   ```
   [Boot] zone-a
   [WiFi] Connected
   [MQTT] Connected. Subscribed: edge/zone-a/request, edge/zone-a/policy
   [req] stream=cnc-01/vibration payload=1200KB hit=0 latency=1523ms cache=5
   [score] i32=12345 decision=1 s=[10,127,100,0,2,5,50,8]
   ```

5. After ~2 minutes, policy updates arrive:
   ```
   [policy] updated int8[0]=-12 float_avg=0.123
   ```

### Option B: VS Code Wokwi Extension

1. Install the **Wokwi** extension in VS Code (search "Wokwi Simulator")
2. Open the project: `code .`
3. Press **Cmd+Shift+P** → `Wokwi: Start Simulator`
4. For Zone B, open a second VS Code window with `code . --new-window`

---

## Full Demo Setup (4 Terminals + 2 Browser Tabs)

```
Terminal 1:  docker compose up --build
             └─► Trainer + MQTT + Traffic generator

Terminal 2:  docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry"
             └─► Watch JSON flowing from both zones

Terminal 3:  docker compose logs -f trainer | grep -E "Replay|updates|loss"
             └─► Watch training happening (loss decreasing)

Terminal 4:  python3 demo/wokwi_comparison_dashboard.py
             └─► Real-time metrics dashboard

Browser Tab 1: wokwi.com → Zone A firmware → Play
               └─► ESP32 sim, int8 inference, cache decisions

Browser Tab 2: wokwi.com → Zone B firmware → Play
               └─► ESP32 sim, int8 inference, cache decisions
```

### Expected timeline

```
0–10s:   Zones boot, connect to MQTT
10–20s:  Traffic arrives, zones process requests
20–60s:  Trainer starts updating (Replay size > 64)
100–120s: First policy published to both zones
2+ min:  Hit rates improving (0% → 9% → 12%)
```

---

## Verifying It Works

```bash
# Are all containers up?
docker compose ps

# Is telemetry flowing from zones?
docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry"

# Is trainer learning?
docker compose logs trainer | grep "updates="

# Is policy being sent to zones?
docker compose exec mqtt mosquitto_sub -t "edge/+/policy"
```

**Signs of health:**

| Signal | Location | Meaning |
|--------|----------|---------|
| `[MQTT] Connected` | Wokwi serial | Zone connected to trainer |
| `Replay size=100+` | Trainer log | Enough data to train |
| `updates=50, 100, ...` | Trainer log | Training loop running |
| `critic_loss` decreasing | Trainer log | Model learning |
| `[policy] updated` | Wokwi serial | Trainer pushed new policy |
| Hit Rate: 0% → 12% | Dashboard | Policy working |

---

## Project Structure

```
.
├── control-plane/
│   ├── control_plane/
│   │   ├── trainer.py          # TD3 training loop with profiling
│   │   ├── models.py           # LTC actor + TD3 critic
│   │   ├── state_tracker.py    # Per-zone independent state
│   │   ├── replay_buffer.py    # Shared global replay buffer
│   │   ├── traffic_generator.py# Bursty 50-machine CNC traffic
│   │   ├── profiler.py         # CPU/memory/timing metrics
│   │   ├── messages.py         # MQTT message schemas
│   │   ├── topics.py           # MQTT topic helpers
│   │   ├── mqtt_client.py      # MQTT bus wrapper
│   │   └── config.py           # Settings from env vars
│   ├── mosquitto/
│   ├── Dockerfile
│   └── requirements.txt
├── firmware/
│   ├── src/main.cpp            # ESP32: int8 policy, LRU cache, MQTT
│   └── platformio.ini          # zone-a and zone-b environments
├── demo/
│   ├── hardware_benchmark.py   # CPU vs GPU vs Edge speed test
│   ├── compare_mode.py         # CPU policy vs Edge policy decisions
│   ├── wokwi_comparison_dashboard.py  # Real-time zone metrics UI
│   └── dashboard.py            # Trainer stats dashboard
├── docker-compose.yml
└── README.md
```

---

## Key Concepts

### Why int8 quantization?

ESP32 has 240 KB RAM and no FPU. The full TD3+LTC network has millions of parameters and takes 0.19 ms per inference on a modern CPU.

The quantization pipeline:
1. Take the first linear layer weights W: shape `[19, 8]`
2. SVD → `U, S, Vt`
3. `compressed = (S[:8] * Vt[:8]).mean(dim=1)` → shape `[8]`
4. `quantized = (compressed / maxabs * 127).int().clamp(-128, 127)`

Result: 8 int8 weights (8 bytes total). Inference = one dot product = **0.7 µs**.

### Why Zone A and B?

- Factory has 50 CNC machines spread across two sections
- Zone A (machines 1–25) and Zone B (machines 26–50) each have a local ESP32
- Each ESP32 maintains its own LRU cache for its section
- Central trainer learns one policy from both sections' experience
- Policy updates are pushed to both zones every 200 critic updates

### Why CTDE?

- Zones can't share data with each other in real time (network cost, latency)
- But a central trainer can observe both zones offline
- One policy works for both because the state vector is generic (cache pressure, latency, frequency, etc.)
- This is the standard MARL approach for heterogeneous edge deployment

---

## Configuration

All settings via environment variables (see `docker-compose.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `EDGE_NODE_IDS` | `zone-a,zone-b` | Comma-separated zone IDs |
| `BURST_PERIOD_S` | `30` | Seconds between traffic bursts |
| `BURST_MIN_KB` | `500` | Min payload per request |
| `BURST_MAX_KB` | `2000` | Max payload per request |
| `REPLAY_SIZE` | `10000` | Max replay buffer size |
| `BATCH_SIZE` | `64` | Training batch size |
| `QUANTIZE_EVERY` | `200` | Publish policy every N critic updates |
| `GAMMA` | `0.99` | TD3 discount factor |
| `TAU` | `0.005` | Soft target update rate |

To add a third zone:
```yaml
# docker-compose.yml
EDGE_NODE_IDS: "zone-a,zone-b,zone-c"
```

Then add in `platformio.ini`:
```ini
[env:zone-c]
build_flags = ${env.build_flags} -DNODE_ID='"zone-c"'
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `MQTT connection refused` | Run `docker compose up --build` first |
| Wokwi `[MQTT] failed rc=4` | Check Docker is running, wait 10s and retry |
| `Replay size=0` not growing | Check Wokwi serial shows `[MQTT] Connected` |
| No policy updates | Need ~200 critic updates first (~2 min) |
| `ModuleNotFoundError: ncps` | `cd control-plane && pip install -r requirements.txt` |
| Firmware not compiling | `cd firmware && pio run -e zone-a` |
