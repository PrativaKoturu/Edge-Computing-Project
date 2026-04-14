# Part 2 — On-Device Q-Learning on ESP32

> **Part 1** (root folder): Train on CPU/GPU, compress to 8 weights, push to ESP32 (CTDE)
> **Part 2** (this folder): ESP32 trains itself from scratch — no central trainer at all

Docker only sends sensor data. The ESP32 runs the full RL training loop.

---

## What is different from Part 1

| | Part 1 (CTDE) | Part 2 (On-Device) |
|--|--------------|-------------------|
| Where training happens | Your laptop (Docker) | ESP32 itself |
| Where inference happens | ESP32 | ESP32 |
| Algorithm | TD3 + LTC (3,878 params) | Q-learning, linear (16 weights) |
| Policy size | 8 int8 weights (compressed) | 16 float32 weights (native) |
| Docker role | Trainer + traffic generator | Traffic generator only |
| Needs laptop to improve? | Yes (trainer must run) | No (ESP32 learns alone) |
| Memory used for RL | N/A on device | 64 bytes (16 floats) |

---

## Algorithm — Q-Learning with Linear Function Approximation

This is the simplest form of deep RL that can run on a microcontroller.

```
Q(s, a) = W[a] · s          ← dot product of weights × state (8 multiplications)

After each request:
  td_error = r + γ · max_a' Q(s', a') - Q(s, a)
  W[a][i] += α · td_error · s[i]    ← weight update (8 multiplications)
```

- **s** — 8-element state vector (cache occupancy, latency, payload, anomaly, hit rate, stream freq, time, pressure)
- **a** — binary action: 0 = skip, 1 = cache
- **r** — reward: +1 hit / −1 miss / −0.001×latency
- **α = 0.05** — learning rate
- **γ = 0.95** — discount factor
- **ε** — epsilon starts at 0.50, decays to 0.05 (explores → exploits)

Total memory for the entire RL model: **64 bytes** (16 float32 weights).

---

## How to Run

### Step 1 — Start the traffic generator (Docker)

From this folder:
```bash
docker compose up --build
```

This starts only the traffic container — no trainer. Docker's only job here is to send CNC sensor data from the AI4I 2020 dataset to the broker.

Wait for:
```
traffic | INFO traffic: Dataset traffic started. node=edge-rl-node period=30.0s
```

### Step 2 — Start the ESP32 in Wokwi

1. Go to **https://wokwi.com/**
2. Click **Start new project** → **ESP32** → **Create**
3. Delete all code in the editor
4. Open `firmware/src/main.cpp`, copy everything, paste into Wokwi
5. Click **▶ Run**

Watch the serial monitor:
```
========================================
 On-Device Q-Learning  [edge-rl-node]
========================================
 alpha=0.050  gamma=0.950  eps=0.50  state=8D
 Training happens entirely on this ESP32.
 No central trainer. No pushed weights.
========================================

[wifi] Connected  ip=10.10.0.2
[mqtt] Connected.  Subscribed: edge/edge-rl-node/request
```

Once requests arrive (every 30 seconds):
```
[req]     stream=cnc-03/vibration             hit=0  lat=1200ms  cache=3
[learn]   action=CACHE  reward=-2.201  td_err=+0.3412  eps=0.499  hit_rate=0.0%

[req]     stream=cnc-07/temperature           hit=0  lat= 900ms  cache=4
[learn]   action=SKIP   reward=-1.900  td_err=-0.1234  eps=0.498  hit_rate=0.0%
```

After ~200 steps (~10 minutes), every 50 steps you will see weights printed:
```
[weights] step=200  eps=0.30  hit_rate=9.5%
  W[CACHE]: +0.1234  -0.0456  +0.2341  +0.4512  +0.1823  +0.2134  -0.0123  -0.0341
  W[SKIP]:  -0.0812  +0.0234  -0.1234  -0.3412  -0.0923  -0.1234  +0.0234  +0.0123
```

These weights are being updated live on the ESP32 — no laptop involved in training.

### Step 3 — Watch learning happen in the monitor

In a new terminal:
```bash
python3 monitor.py
```

Output:
```
  step=  20  MISS   action=CACHE  reward=-2.201  td=+0.3412  eps=0.480  hit_rate=  0.0%
  step=  21  MISS   action=SKIP   reward=-1.900  td=-0.1234  eps=0.479  hit_rate=  0.0%
  step=  40  HIT    action=CACHE  reward=+0.955  td=+0.8123  eps=0.460  hit_rate=  5.0%
  step=  41  MISS   action=CACHE  reward=-2.100  td=-0.2341  eps=0.459  hit_rate=  4.8%
  ...
  step= 200  HIT    action=CACHE  reward=+0.955  td=+0.1234  eps=0.300  hit_rate= 10.2%
```

Watch for:
- `hit_rate` climbing from 0% → 10%+ over ~200 steps
- `td_error` getting smaller (model converging)
- `epsilon` dropping (less random, more policy-driven decisions)
- `action` becoming more consistent (CACHE for frequent streams, SKIP for rare ones)

---

## What to Point to in the Demo

### "Training is happening on the ESP32"

Point to the `[learn]` line in Wokwi serial — it prints after EVERY request:
```
[learn]   action=CACHE  reward=-2.201  td_err=+0.3412  eps=0.499  hit_rate=0.0%
```

Open `firmware/src/main.cpp` and point to lines ~175–185:
```cpp
float tdError = reward + GAMMA * qNext - qCurr;
for (int i = 0; i < STATE_DIM; i++)
    qW[action][i] += ALPHA * tdError * s[i];
```
> "This runs on the ESP32 after every single request. The weights change here, on this $4 chip, with no server involved."

### "The weights are changing over time"

Point to the `[weights]` block printed every 50 steps:
```
W[CACHE]: +0.1234  -0.0456  +0.2341  +0.4512  ...
W[SKIP]:  -0.0812  +0.0234  -0.1234  -0.3412  ...
```
> "These 16 numbers are the entire policy. They started near zero. The ESP32 has been adjusting them through Q-learning. CACHE weights going positive for features like anomaly (s[3]) and stream frequency (s[5]) means: 'cache streams that appear often and have anomalies'."

---

## Part 1 vs Part 2 — The Comparison

This is the core academic contribution: two valid approaches to edge RL.

| Dimension | Part 1: CTDE | Part 2: On-Device |
|-----------|-------------|-------------------|
| Model quality | High (TD3+LTC, 3878 params) | Lower (linear, 16 weights) |
| Autonomy | Needs central trainer | Fully autonomous |
| Memory on device | 8 bytes (int8 weights) | 64 bytes (float32 weights) |
| Training hardware | Laptop / cloud GPU | ESP32 (240MHz, no GPU) |
| Update frequency | Every ~200 critic updates | Every single request |
| Internet dependency | Needs trainer reachable | Only needs data source |
| Best use case | When cloud is available | When device must be self-sufficient |

Neither is better — they solve different constraints.
