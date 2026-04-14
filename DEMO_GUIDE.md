# Demo Guide — What to Show Your Teacher

## Understanding the Problem — Before the Demo

Before showing anything, explain the setting. Every word in the pitch has a specific meaning.

---

### What are CNC Machines?

**CNC = Computer Numerical Control**

CNC machines are automated industrial machines that manufacture precision components by following programmed instructions. They:

- Cut and shape metal parts
- Drill holes to sub-millimetre precision
- Mill, lathe, and grind components

They are used in automotive, aerospace, and electronics manufacturing — anywhere that requires high-volume, high-precision parts. Think of a robotic arm that follows a digital blueprint to produce thousands of identical components.

**Why do they generate sensor data?**

A CNC machine running at full speed is under enormous physical stress. To catch failures before they happen (predictive maintenance), each machine continuously broadcasts:

| Sensor | What it measures | Why it matters |
|--------|-----------------|----------------|
| Vibration | Oscillation of the spindle (mm/s) | Bearing wear, imbalance |
| Temperature | Heat of the cutting process (°C/K) | Overheating, tool wear |
| Torque | Rotational force on the motor (Nm) | Overload, material resistance |
| Rotational speed | Spindle RPM | Feed rate anomalies |
| Tool wear | Minutes of active cutting | Predicts tool failure |

In a factory of 50 machines, each broadcasting 3–5 sensor streams continuously, this is thousands of readings per second. Not all of it needs to be sent to the cloud. That is the problem this system solves.

---

### The Pitch — Broken Down Line by Line

> **"We have 50 CNC machines generating sensor data."**

50 machines, each with vibration, temperature, torque, and wear sensors. Every 30 seconds each machine emits a burst of readings. This is exactly what the AI4I 2020 dataset captures — 10,000 rows of real CNC sensor readings with labelled failure events.

---

> **"A tiny ESP32 edge device decides what to cache locally."**

The ESP32 is a microcontroller the size of a credit card, costing around $4. It sits physically on the factory floor, close to the machines. Its job is to receive incoming sensor stream requests and decide which ones to keep in its local cache (64 slots).

- **Cache hit** → data served locally in 45ms
- **Cache miss** → data fetched from cloud in 800–2000ms

The ESP32 cannot cache everything — 64 slots for 150 possible streams. It must be selective. That selectivity is what the RL policy provides.

---

> **"The ESP32 is too weak to run a neural network."**

Neural networks require floating-point matrix multiplications across thousands of parameters. The ESP32 has:

- 240 MHz CPU (no GPU)
- 240 KB of RAM
- No hardware floating-point accelerator

The full TD3+LTC actor network has 3,878 parameters and takes 0.2ms on a laptop CPU. On an ESP32 it would take orders of magnitude longer and consume more memory than available. It simply cannot run.

---

> **"So we train one on a laptop, compress it to 8 numbers, and send it down."**

This is the core engineering contribution — **model compression for edge deployment**:

1. Train the full TD3+LTC network on a laptop (or cloud server) — thousands of parameters, proper floating-point math
2. Use **SVD (Singular Value Decomposition)** to find the 8 most important directions in the first layer weight matrix
3. Scale those 8 values to integers in the range −128 to +127 (**int8 quantization**)
4. Send those 8 integers to the ESP32 over MQTT

This is the same principle behind **TinyML** and **Edge AI** — taking a model that was trained on powerful hardware and distilling it into something a microcontroller can actually execute.

```
Full model:   3,878 parameters   0.2ms on CPU      cannot run on ESP32
Compressed:   8 integers         0.7µs on ESP32    fits in a single loop
```

The ESP32 then runs:
```cpp
int32_t score = 0;
for (int i = 0; i < 8; i++) {
    score += weight[i] * state[i];   // 8 multiplications
}
bool cache = (score > 0) || anomaly;
```

---

> **"I'll show you both sides running at the same time."**

| Side | Where | What it does |
|------|-------|-------------|
| Laptop (Docker) | Your machine | Trains the full TD3+LTC network, pushes compressed weights |
| ESP32 (Wokwi) | Browser simulation | Runs 8-multiply policy, makes caching decisions at 0.7µs |

Both connected over MQTT via HiveMQ. Both live. Both visible simultaneously.

---

### How the Dataset Fits In

The AI4I 2020 dataset is a real-world recorded version of exactly this scenario:

- Each row = one sensor reading from a CNC machine
- Columns = rotational speed, torque, temperature, tool wear
- `Machine failure` column = real labelled failure events (3.39% of rows)

In the demo, the traffic container replays these rows as MQTT requests — simulating what the physical sensors would publish in a real factory. The ESP32 receives them exactly as it would receive readings from real machines. The only difference is the source: a CSV file on a laptop vs. a sensor chip on a machine.

---

## The Two-Sentence Pitch

> "We have 50 CNC machines generating sensor data. A tiny ESP32 edge device decides what to cache locally. The ESP32 is too weak to run a neural network — so we train one on a laptop, compress it to 8 numbers, and send it down. I'll show you both sides running at the same time."

---

## Step 1 — Show WHERE the model runs on your machine

Open a terminal and run:

```bash
docker compose up --build
```

Wait for both lines:
```
trainer    | INFO trainer: Trainer loop started. Nodes=zone-a
traffic    | INFO traffic: Dataset traffic started. node=zone-a period=30.0s burst_size=20 rows=10000
```

**What to say:**
> "This Docker container is the brain. It runs the full TD3+LTC neural network — 3,878 parameters in the actor, 137,000 in the critic. It reads real CNC machine data from the AI4I 2020 dataset — 10,000 rows of actual rotational speed, torque, and temperature readings from industrial machines."

---

## Step 2 — Show the model actually training

Open a second terminal:

```bash
docker compose logs -f trainer
```

Point to this output as it appears:
```
INFO trainer: Replay size=100  latest node=zone-a  hit=False  lat=1523ms
INFO trainer: updates=50   replay=120  critic_loss(avg10)=0.3421  actor_loss(avg10)=-0.0123
INFO trainer: updates=100  replay=150  critic_loss(avg10)=0.2100  actor_loss(avg10)=-0.0089
INFO trainer: updates=150  replay=180  critic_loss(avg10)=0.1450  actor_loss(avg10)=-0.0067
INFO trainer: updates=200  replay=200  critic_loss(avg10)=0.0980  actor_loss(avg10)=-0.0041
```

**What to say and point to:**
> "`critic_loss` — this number is going down. That means the network's Q-value predictions are getting more accurate. The model is learning which streams are worth caching."

> "Every 200 updates, the trainer compresses the actor network into 8 integers using SVD — that's this line:"
```
INFO trainer: updates=200  ...  publishes=1
```
> "Those 8 integers get sent over the internet to the ESP32 right now."

**The exact code that does this** — open `control-plane/control_plane/trainer.py` and point to the quantization block:
```python
if critic_updates % settings.quantize_every_critic_updates == 0:
    float_w, int8_w = _quantize_policy_weights(agent.actor)
    bus.publish(policy_topic(nid), PolicyUpdate(...).to_json())
```
> "This is where the trained policy leaves your machine and goes to the ESP32."

---

## Step 3 — Show the ESP32 running the policy

Open Wokwi, paste the firmware, click Run. Point to the serial output:

```
Boot node_id=zone-a
MQTT connected. Subscribed: edge/zone-a/request, edge/zone-a/policy
[req] stream=cnc-03/vibration payload=834KB anomaly=0 hit=0 latency=1523ms cache=5
[score] i32=-234 decision=0 s=[10,97,76,0,0,32,8,0]
```

**What to say and point to, line by line:**

| Output | What it means |
|--------|--------------|
| `stream=cnc-03/vibration` | Real stream from the AI4I dataset — machine 3's vibration sensor |
| `payload=834KB` | Scaled from the actual RPM value in that dataset row |
| `anomaly=0` | No machine failure recorded in this row |
| `hit=0 latency=1523ms` | Cache miss — had to fetch from cloud (800–2000ms) |
| `s=[10,97,76,0,0,32,8,0]` | The 8-element state vector (see breakdown below) |
| `i32=-234 decision=0` | Score is negative → don't cache |

**State vector breakdown — point to each number:**
```
s[0] = 10  → cache is 8% full        (5 of 64 slots used)
s[1] = 97  → last fetch was slow      (1523ms, normalized 0–127)
s[2] = 76  → payload is medium size   (834KB, normalized 0–127)
s[3] =  0  → not an anomaly
s[4] =  0  → 0% of last 10 requests were hits
s[5] = 32  → this stream seen 5× in last 20 requests
s[6] =  8  → ~2 seconds since last request
s[7] =  0  → no recent evictions (no cache pressure)
```

**Open `firmware/src/main.cpp` and point to the inference loop:**
```cpp
int32_t score = 0;
for (int i = 0; i < 8; i++) {
    score += (int32_t)policyWeightsInt8[i] * (int32_t)s[i];
}
bool cacheDecision = (score > threshold) || anomaly;
```
> "This is the entire neural network on the ESP32. 8 multiplications. That's it. It runs in 0.7 microseconds."

**After ~2 minutes, point to this line appearing in Wokwi:**
```
[policy] updated int8[0]=-12 float_avg=0.123
```
> "The trainer just pushed new weights here. The ESP32 didn't restart — it swapped the weights in mid-operation. The next `[score]` line uses the trained policy."

---

## Step 4 — Show the proof number (the whole point)

Run this in a third terminal:

```bash
python3 demo/hardware_benchmark.py
```

Point to this output:
```
CPU TD3+LTC (full network):     0.201 ms per inference
Edge int8 (ESP32 simulated):   0.0009 ms  (0.88 µs)
Edge Speedup vs CPU:            227x faster
```

**What to say:**
> "The full neural network on my laptop takes 0.201 milliseconds per decision. The ESP32 takes 0.88 microseconds — 227 times faster. That's not an optimization. That's a completely different computation. The full network has thousands of floating-point operations. The ESP32 version has 8 integer multiplications."

> "Why does this matter? The ESP32 costs $4, runs on a battery, and sits on the factory floor. It cannot run the full network — it has no GPU, barely any RAM, and no floating-point accelerator. But it *can* run 8 multiplications in 0.88 microseconds. That's CTDE: train centrally on powerful hardware, execute on cheap constrained devices."

---

## Step 5 — Show the caching logic improving over time

Keep the dashboard open alongside:

```bash
python3 demo/wokwi_comparison_dashboard.py
```

Point to the 4 status lines as they change:
```
[1/4] Telemetry flowing: 120 transitions in replay buffer         ← data from ESP32 arriving
[2/4] Edge node connected: 45 requests processed on ESP32         ← ESP32 is live
[3/4] RL training running: 200 TD3 updates, critic_loss=0.098     ← model improving
[4/4] Policy pushed to ESP32 1 time(s) — edge using trained weights  ← loop complete
```

**What to say at step 4:**
> "This is the full loop closed. The ESP32 generated experience, the trainer learned from it, compressed the knowledge to 8 numbers, and sent it back. The ESP32 is now making decisions using what the network learned from real industrial failure data."

---

## The Layout for the Demo

Have all of these open at the same time:

```
┌──────────────────────────┬──────────────────────────────┐
│  Terminal                │  Browser (Wokwi)             │
│  docker logs trainer     │  ESP32 serial                │
│                          │                              │
│  critic_loss=0.098 ↓     │  [req] cnc-03/vibration      │
│  updates=200             │  [score] i32=+340 decision=1 │
│  publishes=1             │  [policy] updated int8[0]=12 │
├──────────────────────────┴──────────────────────────────┤
│  Terminal 2                                             │
│  python3 demo/hardware_benchmark.py                     │
│                                                         │
│  CPU: 0.201 ms    Edge: 0.0009 ms    Speedup: 227x      │
└─────────────────────────────────────────────────────────┘
```

| Window | Command | Points to |
|--------|---------|-----------|
| Terminal 1 | `docker compose up --build` | Trainer + dataset traffic running |
| Terminal 2 | `docker compose logs -f trainer` | TD3 loss going down in real time |
| Terminal 3 | `python3 demo/hardware_benchmark.py` | 227x speedup proof |
| Terminal 4 | `python3 demo/wokwi_comparison_dashboard.py` | Live 4-stage pipeline status |
| Browser | wokwi.com | ESP32 serial: requests, scores, policy updates |

**Three things the teacher sees simultaneously:**
1. Neural network training in real time (critic loss going down)
2. ESP32 making decisions using that network (scores + decisions in serial)
3. The speed proof (227× — why the full network can't be on the ESP32)

---

## Where Does the ESP32 Get Its Data From?

The ESP32 never reads the CSV directly. The data travels through three hops:

```
Your Machine                    Internet                  Wokwi (Browser)
────────────────                ────────                  ───────────────
traffic container
  reads row from   ──publishes──▶  broker.hivemq.com  ──delivers──▶  ESP32
  data/ai4i2020.csv               edge/zone-a/request
  builds JSON msg
```

Step by step:
1. **Traffic container** reads the next row from `data/ai4i2020.csv`
2. Converts it to a small JSON message: `{"stream_id":"cnc-03/vibration","payload_kb":834,"anomaly":false}`
3. **Publishes** it to topic `edge/zone-a/request` on `broker.hivemq.com`
4. HiveMQ holds it and **delivers** it to anyone subscribed to that topic
5. **ESP32 in Wokwi** is subscribed — it receives the message and makes a caching decision

The ESP32 has no idea the data came from a real industrial dataset. It just sees one small JSON message at a time: a stream ID, a payload size, and an anomaly flag.

---

## "But We Still Need a Laptop — Is This Really Edge Computing?"

Yes — and this is the most important concept to understand.

### What "edge computing" actually means

Edge computing does **not** mean the ESP32 works completely offline forever. It means **the decision that needs to be fast happens on the device, not in the cloud.**

Without edge computing, every caching decision would require a round trip to a server:
```
Sensor arrives → send to cloud → cloud decides → send answer back → act
Total latency: 800–2000ms per decision (network round trip)
```

With this system:
```
Sensor arrives → ESP32 decides locally in 0.7µs → act
Total latency: 0.7 microseconds (no network involved)
```

### What the laptop is needed for vs. not needed for

| Task | Needs laptop? | Why |
|------|:------------:|-----|
| Making caching decisions | **No** | ESP32 runs the int8 policy locally |
| Serving cached data (45ms) | **No** | Cache lives on the ESP32 itself |
| Working if internet goes down | **No** | Uses last received policy, keeps deciding |
| Receiving new sensor requests | **Yes** | Traffic generator sends them (in demo) |
| Getting smarter over time | **Yes** | Trainer improves the policy |
| Pushing updated weights | **Yes** | But only once every ~2 minutes, not per-decision |

### The key distinction: per-decision vs. periodic

The laptop is involved **periodically** (every ~2 minutes to push new weights). The ESP32 makes decisions **continuously** (every 30 seconds in the demo, could be every millisecond in production) without touching the laptop at all.

### In a real deployment, the laptop becomes a cloud server

In production this system would look like:

```
Factory Floor                        Cloud (always-on server, not your laptop)
─────────────────                    ─────────────────────────────────────────

ESP32 edge node                      Central RL trainer (AWS / Azure / data center)
  • makes decisions locally            • trains on telemetry from all factories
  • 0.7µs per cache decision           • pushes updated policy every few hours
  • works even if cloud is down        • one server handles hundreds of factories
  • only sends small telemetry back
```

The demo uses your laptop because this is a class project. The architecture is identical to a real deployment — the only difference is the "cloud server" is your laptop instead of AWS.

### The actual edge computing claim

> **The decision that needs to be fast (cache or not, 0.7µs) happens on the device at the edge — not in the cloud. The device does not need a round trip to a server for every sensor reading.**

Training and policy improvement happen centrally on a slow schedule (minutes). Execution happens on the device at microsecond speed, locally, always. That is edge computing.

---

## Real-World Data Flow (How It Would Work in a Real Factory)

In the demo, your laptop plays the role of the CNC machines. In a real deployment, the machines themselves send data directly. Here is how the full flow changes.

### Demo vs. Real World

```
DEMO (what we have now)
───────────────────────
CSV file on laptop
    → Docker traffic container (pretends to be 50 machines)
        → HiveMQ broker
            → ESP32 edge node


REAL WORLD
──────────
Actual CNC machine
    → sensor chip on the machine (reads vibration/temp/pressure)
        → sends data over factory WiFi or wired ethernet
            → MQTT broker (could be local or cloud)
                → ESP32 edge node
```

### Real-World Component by Component

**1. The sensor on the machine**

Each CNC machine would have a small sensor module attached to it — an accelerometer for vibration, a thermocouple for temperature, a pressure transducer. These are standard industrial components costing $10–50 each.

The sensor chip reads a value (e.g., vibration = 0.73 mm/s) and needs to send it somewhere.

**2. How the sensor sends data**

The sensor publishes an MQTT message — exactly the same format our traffic generator uses:
```json
{"stream_id": "cnc-03/vibration", "payload_kb": 834, "anomaly": false}
```

It sends this to an MQTT broker. In a factory this broker would typically be:
- A **local broker on-premises** (e.g., Mosquitto running on a Raspberry Pi in the factory) — fast, works without internet
- Or a **cloud broker** like AWS IoT Core, Azure IoT Hub, or HiveMQ Cloud

**3. The MQTT broker**

The broker receives messages from all 50 machines and routes them to whoever is subscribed. In our demo this is HiveMQ's free public broker. In a real factory it would be a dedicated broker that the company controls, for security and reliability.

**4. The ESP32 edge node**

The ESP32 is physically located in the factory — mounted on a DIN rail in the electrical cabinet, or on the machine itself. It is subscribed to the request topics for all machines it is responsible for. It receives each message, runs the int8 policy in 0.7µs, decides what to cache, and publishes telemetry back.

**5. The central trainer**

Instead of Docker on your laptop, this would be a server — on-premises or in the cloud. It is always running, always collecting telemetry, always training. It pushes updated weights to the ESP32 over MQTT every few hours.

### Full Real-World Architecture

```
Factory Floor
─────────────────────────────────────────────────────

[CNC Machine 01]──sensor──┐
[CNC Machine 02]──sensor──┤
[CNC Machine 03]──sensor──┤──► Local MQTT Broker ──► ESP32 Edge Node
        ...                │    (Raspberry Pi /       • 64-item LRU cache
[CNC Machine 50]──sensor──┘     factory server)       • int8 policy (0.7µs)
                                                       • serves cache hits locally
                                      │                  at 45ms
                                      │ telemetry
                                      ▼
                              Cloud / Data Center
                              ─────────────────────
                              Central RL Trainer
                              • TD3+LTC full network
                              • trains on all telemetry
                              • every few hours:
                                compress → int8 → push
                                back to ESP32
```

### What stays the same vs. what changes

| Component | In Demo | In Real World |
|-----------|---------|---------------|
| Sensor data source | CSV file on laptop | Physical sensors on machines |
| Who sends requests | Docker traffic container | Sensor chips via factory WiFi |
| MQTT broker | HiveMQ free public | Dedicated broker (local or cloud) |
| ESP32 | Wokwi browser simulation | Real ESP32 hardware on factory floor |
| Trainer | Docker on your laptop | Cloud server or on-premises server |
| Policy updates | Every ~2 minutes (demo) | Every few hours (production) |
| Caching decision speed | 0.7µs (same) | 0.7µs (same) |

### Why MQTT specifically?

MQTT was designed for exactly this — constrained IoT devices on unreliable networks:
- Messages are tiny (just JSON, a few hundred bytes)
- Works over slow or unstable connections
- The broker handles delivery — the sensor just fires and forgets
- Standard protocol supported by every industrial IoT platform (AWS IoT, Azure IoT, Google Cloud IoT)

The code does not change at all between demo and production. You only change the broker address from `broker.hivemq.com` to your factory's broker IP. Everything else — the ESP32 firmware, the trainer, the policy format — is identical.

---

## Quick Answers to Likely Teacher Questions

**Q: Where is the RL actually happening?**
> Two places. Training (improving the policy) happens in Docker on your CPU — that's the `critic_loss` going down. Inference (using the policy to decide) happens on the ESP32 — that's the `[score]` line every 30 seconds.

**Q: What is the dataset?**
> AI4I 2020 Predictive Maintenance dataset from UCI Machine Learning Repository. 10,000 rows of real CNC machine sensor readings — rotational speed, torque, temperature, tool wear — with 339 labelled machine failure events (3.39% of rows).

**Q: What does the reward function look like?**
```python
reward = +1.0   if cache hit
       - 1.0   if cache miss
       - 0.001 × latency_ms        (penalise slowness)
       + 0.5   × anomaly × hit     (bonus for caching failure events)
       - 0.3   × cache_pressure    (penalise evicting too aggressively)
```

**Q: Why TD3 and not a simpler algorithm like Q-learning?**
> The caching decision is a continuous action (a score from 0 to 1, not just "cache" or "don't"). TD3 handles continuous action spaces. Its twin critics also prevent Q-value overestimation, which makes training more stable on noisy IoT data.

**Q: Why LTC for the actor?**
> Cache decisions depend on history — whether a stream has been requested repeatedly, how long ago, whether there's a trend. LTC (Liquid Time-Constant) networks have a built-in time constant, so they naturally model temporal patterns without needing an explicit RNN hidden state management.

**Q: How does the quantization work?**
> SVD (Singular Value Decomposition) of the first layer weight matrix [19×8]. Take the top 8 singular values, collapse to a single 8-element vector, scale to [-127, 127] as int8. This discards the less important components and fits the result into 8 integers the ESP32 can multiply.

**Q: What is CTDE?**
> Centralized Training, Decentralized Execution. The idea: use a powerful central machine to train a good policy, then compress and deploy it to cheap constrained devices. The ESP32 never needs to run backpropagation — it only runs inference, which is just 8 multiplications.

**Q: If you close the laptop, does the ESP32 stop working?**
> It stops receiving new requests (because the traffic generator is on the laptop) and stops getting policy updates (because the trainer is on the laptop). But the ESP32 itself keeps running and keeps using the last policy it received. In a real deployment the laptop is replaced by a cloud server that runs 24/7 — the architecture is identical, just the hardware changes.

**Q: Why does the ESP32 need the laptop at all then?**
> Two reasons. First, in the demo the laptop generates the sensor requests — in a real factory those would come from actual machines. Second, the laptop improves the policy over time via RL training and pushes better weights. The ESP32 can run indefinitely on old weights, but it gets smarter only when the trainer pushes an update.

**Q: What happens if the internet connection drops?**
> The ESP32 keeps making decisions using its current weights — it never needs the internet per-decision. The MQTT connection to HiveMQ will drop and reconnect automatically when the network comes back. Any telemetry generated while offline is lost, but the edge device never stops operating.
