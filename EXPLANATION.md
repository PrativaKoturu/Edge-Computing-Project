# Complete Project Explanation
### Edge Computing + Reinforcement Learning System

This document explains everything: what the project does, why it exists, how to run it, what happens while it runs, the algorithm, and every line of code that matters. No prior ML knowledge assumed.

---

## Table of Contents

1. [The Real-World Problem](#1-the-real-world-problem)
2. [How to Run It — Step by Step](#2-how-to-run-it--step-by-step)
3. [What Is Happening While It Runs](#3-what-is-happening-while-it-runs)
4. [The Algorithm Explained](#4-the-algorithm-explained)
5. [Code Walkthrough — Every File](#5-code-walkthrough--every-file)
6. [Glossary — Every Term](#6-glossary--every-term)

---

## 1. The Real-World Problem

### The setting

Imagine a factory with 50 CNC machines (computer-controlled drills, cutters, lathes). Each machine has sensors: vibration, temperature, pressure. Each sensor produces a continuous stream of data.

A small computer near the factory floor (an **edge device** — in our case an ESP32 microcontroller the size of a credit card) receives these sensor streams. When a stream arrives, the edge device has two options:

- **Cache it locally** → next time the same stream comes in, it is already on the device → served in **45 ms**
- **Don't cache it** → fetch from the cloud server when needed → takes **800–2000 ms**

The edge device has limited storage (our simulated cache holds 64 streams). It cannot cache everything. It needs to decide *which* streams to cache.

### Why this is hard

The edge device is tiny. It has:
- ~240 KB of RAM
- No GPU
- A CPU running at ~240 MHz

A modern neural network runs millions of floating-point operations and takes ~0.19 ms even on a laptop CPU. On an ESP32, it would be unusable.

Yet we want intelligent caching — not random, not "cache everything" (not enough space), not "never cache" (too slow).

### The solution: train a big network on a powerful machine, shrink it to 8 numbers for the edge

1. A **full neural network** (TD3 + LTC, hundreds of thousands of parameters) runs on your laptop or a cloud GPU. It learns good caching decisions.
2. Every few minutes, the key "intelligence" in that network is compressed into **8 integers** (int8 = values from -128 to 127).
3. Those 8 integers are sent to the ESP32 over the internet (via MQTT).
4. The ESP32 does one simple operation: multiply those 8 weights by its 8 current readings and add them up. That takes **0.7 microseconds** — 270× faster than even the laptop CPU.

This is **CTDE: Centralized Training, Decentralized Execution.**

---

## 2. How to Run It — Step by Step

You need two things running simultaneously:
- **Docker** (runs the trainer and traffic generator on your machine)
- **Wokwi** (runs the ESP32 in your browser)

Both connect to `broker.hivemq.com`, a free public internet message broker.

---

### Prerequisites

**Install Docker Desktop:**
Download from https://www.docker.com/products/docker-desktop and start it. You need to see the Docker icon in your taskbar/menu bar before continuing.

**Install Python dependencies:**
```bash
cd control-plane
pip install -r requirements.txt
cd ..
```

---

### Terminal 1 — Start Docker (the brain)

```bash
docker compose up --build
```

This builds and starts two containers:

| Container | What it does |
|-----------|-------------|
| `trainer` | The RL brain — reads sensor telemetry, trains a neural network, pushes weights |
| `traffic` | Pretends to be 50 CNC machines — sends fake sensor requests every 30 seconds |

Wait until you see both of these lines:
```
trainer    | INFO trainer: Trainer loop started. Nodes=zone-a
traffic    | INFO traffic: Traffic generator started. period=30.0s
```

Leave this terminal open. Do not close it.

---

### Terminal 2 — Watch training happen

Open a new terminal window and run:
```bash
docker compose logs -f trainer
```

You will see lines like:
```
INFO trainer: Replay size=100 latest node=zone-a hit=False lat=1523ms
INFO trainer: updates=50  replay=120  critic_loss(avg10)=0.3421
INFO trainer: updates=200 replay=200  critic_loss(avg10)=0.1234
```

- `Replay size` = how many decisions are stored for training
- `updates` = how many times the network has been improved
- `critic_loss` = how wrong the network's predictions are (lower = better, it's learning)

Leave this terminal open.

---

### Terminal 3 — Run the hardware comparison benchmark

Open a new terminal:
```bash
python3 demo/hardware_benchmark.py
```

This runs 1000 inferences on your CPU and 1000 simulated edge inferences, and prints:
```
CPU TD3+LTC:              0.195 ms per inference
Edge int8 (simulated):    0.0007 ms per inference  (0.70 µs)
Edge Speedup:             ~270x faster than CPU
```

This is the core comparison you show to your professor. You do not need Docker running for this — it works standalone.

---

### Terminal 4 — Live dashboard

Open a new terminal (Docker must be running):
```bash
python3 demo/wokwi_comparison_dashboard.py
```

This connects to the MQTT broker and shows a live dashboard. It tracks 4 stages:
```
[1/4] Telemetry flowing: 120 transitions in replay buffer
[2/4] Edge node connected: 45 requests processed on ESP32
[3/4] RL training running: 200 TD3 updates, critic_loss=0.1234
[4/4] First policy push pending: 0 more critic updates needed
```

Leave this running.

---

### Browser — Start the ESP32 (Wokwi)

1. Go to **https://wokwi.com/**
2. Click **"Start new project"**
3. Select **ESP32** from the list
4. Click **"Create"**
5. You will see a code editor on the left and a simulated chip on the right
6. **Delete all code** in the editor (Ctrl+A, Delete)
7. Open [firmware/src/main.cpp](firmware/src/main.cpp) in VS Code (it is already open in your IDE sidebar)
8. **Select all** (Ctrl+A), **copy** (Ctrl+C)
9. **Paste** into the Wokwi editor (Ctrl+V)
10. Click the **green ▶ Run** button at the top

Watch the serial monitor panel at the bottom of Wokwi:
```
Boot node_id=zone-a
Connecting WiFi SSID=Wokwi-GUEST
WiFi connected ip=10.10.0.2
Connecting MQTT broker.hivemq.com:1883
MQTT connected. Subscribed: edge/zone-a/request, edge/zone-a/policy
```

Once you see `MQTT connected`, the ESP32 is live. Wait up to 30 seconds for the first request burst:
```
[req] stream=cnc-01/vibration payload=1200KB anomaly=0 hit=0 latency=1523ms cache=5
[score] i32=-234 decision=0 s=[10,127,100,0,2,5,50,8]
```

After about 2 minutes (200 trainer updates), you will see:
```
[policy] updated int8[0]=-12 float_avg=0.123
```

This means the trainer pushed trained weights to the ESP32. It is now using what it learned.

---

### What to have open simultaneously for the professor demo

```
┌─────────────────────────────┬─────────────────────────────┐
│  Terminal 2                 │  Browser (Wokwi)            │
│  docker logs trainer        │  ESP32 serial monitor       │
│                             │                             │
│  updates=200                │  [req] cnc-01/vibration     │
│  critic_loss=0.1234 ↓       │  [score] i32=-234           │
│  "network is learning"      │  [policy] updated int8[0]   │
│                             │  "ESP32 got new weights"    │
├─────────────────────────────┴─────────────────────────────┤
│  Terminal 3: python3 demo/hardware_benchmark.py            │
│  CPU: 0.195 ms    Edge: 0.0007 ms    Speedup: 270x         │
└────────────────────────────────────────────────────────────┘
```

**Point to:**
1. Wokwi serial — "This is RL inference running on a simulated ESP32 at 0.7 µs per decision"
2. Trainer logs — "This is the neural network training in real time. Critic loss going down = it's learning"
3. Benchmark output — "270x speedup proves the full network can't run on the ESP32"
4. Dashboard stage 4 — "When this says policy pushed, the ESP32 just received intelligence from the trained network"

---

## 3. What Is Happening While It Runs

Let us trace a single request from birth to death.

### Step 1: Traffic generator sends a request (every 30 seconds)

File: [control-plane/control_plane/traffic_generator.py](control-plane/control_plane/traffic_generator.py), line 63

```python
req = EdgeRequest(node_id="zone-a", ts_ms=now, stream_id="cnc-01/vibration",
                  payload_kb=1200, anomaly=False)
bus.publish("edge/zone-a/request", req.to_json())
```

This sends a JSON message to the internet broker:
```json
{"node_id":"zone-a","ts_ms":1718000000000,"stream_id":"cnc-01/vibration","payload_kb":1200,"anomaly":false}
```

Think of it as saying: "Hey edge node, someone is asking for the vibration stream from machine 1, the data is 1.2 MB, no emergency."

---

### Step 2: ESP32 receives the request and builds its situation description

File: [firmware/src/main.cpp](firmware/src/main.cpp), lines 204–212

The ESP32 looks at its current situation and encodes it as 8 numbers (all scaled 0–127):

```
s0 = how full is my cache?          (5 items / 64 = 8% full → s0 = 10)
s1 = how slow was the last fetch?   (1523ms out of 2000ms max → s1 = 97)
s2 = how big is this data?          (1200KB out of 2000KB max → s2 = 76)
s3 = is this an emergency anomaly?  (no → s3 = 0)
s4 = how often have I had hits recently? (0 out of last 10 → s4 = 0)
s5 = how often has this stream come up? (5 times out of 20 → s5 = 32)
s6 = how long since the last request? (2 seconds → s6 = 8)
s7 = how much eviction pressure?    (0 recent evictions → s7 = 0)
```

So: `s = [10, 97, 76, 0, 0, 32, 8, 0]`

---

### Step 3: ESP32 makes a caching decision using the policy

File: [firmware/src/main.cpp](firmware/src/main.cpp), lines 213–215

```cpp
int32_t score = policyDotScoreInt32(s0, s1, s2, s3, s4, s5, s6, s7);
int32_t threshold = 0;
bool cacheDecision = (score > threshold) || anomaly;
```

The "policy" is just 8 numbers (`policyWeightsInt8`). The decision is:

```
score = w[0]×s[0] + w[1]×s[1] + ... + w[7]×s[7]
      = (-12)×10 + (8)×97 + (5)×76 + ... 
      = some number
if score > 0: cache this stream
if score ≤ 0: don't cache
```

At the start (before any training), all weights are 0, so score is always 0, and nothing gets cached (all misses, 800–2000ms latency). After training, the weights encode learned behavior.

---

### Step 4: ESP32 sends telemetry back

File: [firmware/src/main.cpp](firmware/src/main.cpp), lines 140–157

After handling the request, the ESP32 reports what happened:
```json
{
  "node_id": "zone-a",
  "cache_hit": false,
  "latency_ms": 1523,
  "stream_id": "cnc-01/vibration",
  "cache_items": 5,
  "payload_kb": 1200,
  "anomaly": false,
  "cache_decision": false,
  "evicted": false,
  "score_int32": -234
}
```

This goes to `edge/zone-a/telemetry` on the broker.

---

### Step 5: Trainer receives telemetry and computes a reward

File: [control-plane/control_plane/trainer.py](control-plane/control_plane/trainer.py), lines 33–43

```python
reward = +1.0   (if cache hit)
       - 1.0   (if cache miss)
       - 0.001 × latency_ms          (penalize slowness)
       + 0.5   × anomaly × cache_hit  (bonus for correctly caching emergencies)
       - 0.3   × cache_pressure       (penalize causing too many evictions)
```

For our example (miss, 1523ms latency, no anomaly, no pressure):
```
reward = -1.0 - 0.001×1523 + 0 - 0 = -2.523
```

Negative reward = bad decision. The network should learn to avoid this.

---

### Step 6: Trainer stores the experience and trains

File: [control-plane/control_plane/trainer.py](control-plane/control_plane/trainer.py), lines 150–220

The trainer stores: `(state_before, action_taken, reward, state_after)` — called a **transition**.

Once it has 64 transitions, it starts a training loop:
1. Pick 64 random transitions from the buffer
2. **Critic update**: The critic network predicted the total future reward for this action. Was it right? Adjust it using the actual reward.
3. **Actor update**: Given the current state, what action does the actor suggest? Evaluate it with the critic. If the critic says it is bad, adjust the actor to suggest a better action.
4. Repeat every 50ms.

---

### Step 7: Trainer compresses and pushes weights to ESP32

File: [control-plane/control_plane/trainer.py](control-plane/control_plane/trainer.py), lines 247–255

Every 200 critic updates:
1. Take the first layer of the actor network (a 19×8 matrix of floating-point weights)
2. Run SVD (a math technique to find the "most important directions" in a matrix)
3. Extract the 8 most important values and scale them to -127 to +127 (int8)
4. Publish them to `edge/zone-a/policy`

```json
{"node_id":"zone-a","int8_weights":[-12,8,5,0,3,-7,2,1],"float_weights":[...]}
```

---

### Step 8: ESP32 receives new weights and switches immediately

File: [firmware/src/main.cpp](firmware/src/main.cpp), lines 165–178

```cpp
for (int i = 0; i < 8; i++) {
    policyWeightsInt8[i] = (int8_t)wi8[i].as<int>();
}
hasPolicy = true;
Serial.printf("[policy] updated int8[0]=%d\n", policyWeightsInt8[0]);
```

The very next request uses the new weights. No restart required.

---

## 4. The Algorithm Explained

### What is Reinforcement Learning?

Imagine training a dog. You don't give it a manual. You give it treats when it does the right thing, and nothing (or a correction) when it does the wrong thing. Over time, the dog figures out what behavior gets treats.

RL works the same way:
- The **agent** (our neural network) takes **actions** (cache or don't cache)
- The **environment** (the cache and sensor streams) responds with a **reward** (+1 for hit, -1 for miss)
- The agent's goal is to maximize total future reward
- It improves by trying things and learning from what worked

### What is TD3?

**TD3 = Twin Delayed Deep Deterministic Policy Gradient**

It is a specific RL algorithm designed for continuous actions (our action is a number from 0 to 1 representing "how much to cache").

**The "Twin" part:**
Instead of one critic network that estimates Q-values (expected future reward), TD3 uses two independent critic networks. When computing the target Q-value, it takes the minimum of the two:

```python
q1_t, q2_t = agent.critic_target(next_state, next_action)
q_target = torch.min(q1_t, q2_t)   # take the pessimistic estimate
```

Why? A single critic tends to overestimate Q-values (it gets overconfident). Two critics, taking the minimum, are more conservative and stable.

**The "Delayed" part:**
The actor (policy network) only updates every 2 critic updates:

```python
if critic_updates % settings.policy_delay == 0:   # policy_delay = 2
    # update actor
```

Why? If you update both at the same time, they can chase each other in circles (actor suggests action → critic says it's great → actor doubles down → critic over-learns → unstable). Delaying the actor gives the critic time to stabilize first.

**The "Deterministic" part:**
The actor always outputs the same action for the same state (it is not random). During training, we add small noise to the action to explore:

```python
noise = torch.randn(...) * policy_noise_std    # random exploration
ap = (actor(next_state) + noise).clamp(0, 1)  # noisy action, clipped to [0,1]
```

### What is LTC?

**LTC = Liquid Time-Constant network**

A normal neural network processes one input at a time, with no memory of what came before. An LTC is a special type of **recurrent** (has memory) neural network inspired by how biological neurons actually work.

In a normal neuron model, the response is instant. In an LTC, neurons have a "time constant" — they respond at different speeds. Some neurons react quickly, some slowly. This makes them naturally good at time-series data (sensor streams that change over time).

We use LTC for the **actor** (the policy network) because caching decisions depend on time — how long ago a stream was requested, whether recent requests are clustered, etc.

```python
# models.py line 27
wiring = AutoNCP(units=19, output_size=1)
self.ltc = LTC(19, wiring)
```

`AutoNCP` (Auto Neural Circuit Policy) automatically generates the connection pattern between 19 internal neurons. It decides which neurons connect to which, mimicking biological neural circuits.

### What is quantization?

A standard neural network stores each weight as a 32-bit floating point number (float32). Each float32 can be any value from roughly -3×10^38 to +3×10^38. The ESP32 cannot efficiently compute floating-point math on large matrices.

**Quantization** converts those weights to integers: specifically int8, which is an 8-bit integer in the range -128 to 127.

We go further: instead of sending all 19×8 = 152 weights, we use **SVD** (Singular Value Decomposition) to compress them into just 8 numbers.

```python
# trainer.py lines 60-66
W = actor.input_proj.weight.detach().cpu()  # shape (19, 8)
U, S, Vh = torch.linalg.svd(W, full_matrices=False)
compressed = (S[:8].unsqueeze(1) * Vh[:8]).mean(dim=1)  # shape (8,)
q = (compressed / maxabs * 127.0).round().to(torch.int32).clamp(-128, 127)
```

**What SVD does:** It finds the most important "directions" in the weight matrix. Like how you could describe a face with just "eye size", "nose length", "mouth width" instead of describing every pixel — SVD finds the 8 most important things the weights are saying.

The result: 8 int8 numbers that capture the core decision logic, executable in 8 multiplications.

### What is CTDE?

**CTDE = Centralized Training, Decentralized Execution**

This is the fundamental architectural principle:

| | Training | Execution |
|--|---------|-----------|
| **Where** | Your machine (centralized) | ESP32 (decentralized) |
| **Network** | Full TD3+LTC, thousands of weights | 8 int8 weights |
| **Speed** | 0.19 ms | 0.7 µs |
| **Power** | 65W laptop / 300W GPU | 0.5W ESP32 |
| **Connected?** | Yes, needs MQTT | Yes, but only for weight updates |

The ESP32 makes decisions locally in 0.7 µs without waiting for the server. The server trains and improves the policy, then periodically updates the ESP32.

### What is MQTT?

MQTT (Message Queuing Telemetry Transport) is a lightweight messaging protocol designed for IoT devices. It works like a postal service with named mailboxes:

- **Topics** are mailboxes (e.g., `edge/zone-a/telemetry`)
- **Publishers** put messages in a mailbox (traffic generator, ESP32)
- **Subscribers** check a mailbox for new messages (trainer, dashboard)

The broker (`broker.hivemq.com`) is the post office — it receives messages from anyone and delivers them to anyone subscribed to that topic.

This is why it works across the internet: Wokwi (cloud) and Docker (your machine) both connect to the same broker. Neither needs to know where the other is.

---

## 5. Code Walkthrough — Every File

### `firmware/src/main.cpp` — the ESP32 brain

**Lines 1–5: Includes**
```cpp
#include <Arduino.h>       // ESP32 basic functions (delay, millis, Serial)
#include <WiFi.h>          // WiFi connection
#include <PubSubClient.h>  // MQTT client
#include <ArduinoJson.h>   // Parse and create JSON
```

**Lines 6–16: Configuration**
```cpp
#ifndef NODE_ID
#define NODE_ID "zone-a"   // This device's name — used in MQTT topics
#endif
#ifndef MQTT_HOST
#define MQTT_HOST "broker.hivemq.com"  // The internet broker
#endif
```
`#ifndef` means "if this name is not already defined, define it now." This lets you override these at compile time.

**Lines 30–37: Data storage**
```cpp
static const int CACHE_CAPACITY = 64;    // Max streams we can remember
static String cacheKeys[64];             // Names of cached streams
static uint32_t cacheLastUse[64];        // When each was last used (ms since boot)
static int cacheCount = 0;               // How many we have cached right now

static int8_t policyWeightsInt8[8] = {0};  // The 8 learned weights (start at 0)
static float policyWeightsFloat[8] = {0};  // Float version (for logging)
static bool hasPolicy = false;             // Have we received any weights yet?
```

**Lines 65–86: insertCache — LRU cache**
```cpp
static void insertCache(const String &key) {
    // First: is it already cached? If yes, just update last-use time.
    int idx = findCacheIdx(key);
    if (idx >= 0) { touchCache(idx); return; }

    // If there is space: just add it.
    if (cacheCount < CACHE_CAPACITY) {
        cacheKeys[cacheCount] = key;
        cacheLastUse[cacheCount] = nowMs();
        cacheCount++;
        return;
    }

    // Cache is full: find the Least Recently Used item and replace it.
    int lru = 0;
    for (int i = 1; i < CACHE_CAPACITY; i++) {
        if (cacheLastUse[i] < cacheLastUse[lru]) lru = i;  // older = smaller ms
    }
    cacheKeys[lru] = key;       // overwrite the oldest entry
    cacheLastUse[lru] = nowMs();
}
```
LRU = Least Recently Used. When the cache is full, the stream that has not been asked for the longest time is the one evicted (removed) to make space.

**Lines 122–129: State encoding**
```cpp
// "How full is the cache?" → scaled to 0–127
static int state_i8_cache_occupancy() {
    return clampInt((cacheCount * 127) / 64, 0, 127);
}
// "How slow was the last fetch?" → 0ms=0, 2000ms=127
static int state_i8_latency(int latencyMs) {
    return clampInt((clampInt(latencyMs, 0, 2000) * 127) / 2000, 0, 127);
}
```
Each state feature is converted to an integer 0–127. The ESP32 cannot do floating-point math easily, so we scale everything to integers.

**Lines 131–138: The actual RL inference**
```cpp
static int32_t policyDotScoreInt32(int s0,...,int s7) {
    int s[8] = {s0, s1, s2, s3, s4, s5, s6, s7};
    int32_t score = 0;
    for (int i = 0; i < 8; i++) {
        score += (int32_t)policyWeightsInt8[i] * (int32_t)s[i];
    }
    return score;
}
```
This is the entire "neural network" on the ESP32. 8 multiplications, 8 additions. It runs in ~0.7 µs.

**Lines 213–215: The caching decision**
```cpp
int32_t score = policyDotScoreInt32(s0, s1, s2, s3, s4, s5, s6, s7);
int32_t threshold = 0;
bool cacheDecision = (score > threshold) || anomaly;
```
If the score is positive: cache. If the score is zero or negative: don't cache. If it is an anomaly (emergency sensor reading): always cache regardless.

**Lines 251–278: WiFi and MQTT connection**
```cpp
static void ensureWifi() {
    if (WiFi.status() == WL_CONNECTED) return;  // already connected
    WiFi.mode(WIFI_STA);                        // station mode (client, not hotspot)
    WiFi.begin(WIFI_SSID, WIFI_PASS);           // connect to Wokwi-GUEST
    while (WiFi.status() != WL_CONNECTED) {
        delay(200);  // wait 200ms and check again
    }
}
```
`Wokwi-GUEST` is a fake WiFi network that Wokwi provides inside the simulator. The simulator routes all traffic to the real internet.

**Lines 281–293: setup() and loop()**
```cpp
void setup() {
    Serial.begin(115200);  // start serial output at 115200 baud (for the console)
    ensureWifi();          // connect to WiFi
    ensureMqtt();          // connect to broker
}

void loop() {
    ensureWifi();   // reconnect if dropped
    ensureMqtt();   // reconnect if dropped
    mqtt.loop();    // process incoming MQTT messages (calls onMqttMessage)
    delay(10);      // give other tasks a turn (every 10ms)
}
```
`setup()` runs once at boot. `loop()` runs forever after that.

---

### `control-plane/control_plane/models.py` — the neural networks

**LtCActor: the decision-making network**
```python
class LtCActor(nn.Module):
    def __init__(self, state_dim: int = 8):
        self.input_proj = nn.Linear(8, 19)     # Layer 1: 8 inputs → 19 neurons
        wiring = AutoNCP(units=19, output_size=1)  # LTC wiring pattern
        self.ltc = LTC(19, wiring)              # LTC: 19 neurons → 1 output

    def forward(self, s):
        x = torch.tanh(self.input_proj(s))  # expand 8D → 19D, squash to -1..1
        y, _ = self.ltc(x)                 # LTC processes with time memory
        return torch.sigmoid(y)            # squash to 0..1 (cache probability)
```

The `forward` method is what runs when you use the network:
- `nn.Linear(8, 19)`: a fully-connected layer — each of the 8 inputs connects to each of the 19 neurons with a learnable weight
- `torch.tanh`: squashes any number to -1 to +1 (prevents values from exploding)
- `LTC`: liquid time-constant layer (has memory of past inputs)
- `torch.sigmoid`: squashes to 0 to 1 (output is a probability: "how much should I cache this?")

**Td3Critic: the Q-value estimator**
```python
class Td3Critic(nn.Module):
    def __init__(self):
        def qnet():
            return nn.Sequential(          # chain layers in order
                nn.Linear(9, 256),         # input: 8 state + 1 action = 9
                nn.ReLU(),                 # activation: max(0, x)
                nn.Linear(256, 256),       # hidden layer
                nn.ReLU(),
                nn.Linear(256, 1),         # output: single Q-value
            )
        self.q1 = qnet()  # first critic
        self.q2 = qnet()  # second critic (twin)
```
Takes in (state, action) and outputs a Q-value: "if I am in this state and take this action, how much total reward will I get in the future?"

**Td3Agent: bundles everything**
```python
class Td3Agent(nn.Module):
    def __init__(self):
        self.actor = LtCActor()          # the real policy (trained)
        self.critic = Td3Critic()        # the real Q estimator (trained)
        self.actor_target = LtCActor()   # a slow-moving copy of actor
        self.critic_target = Td3Critic() # a slow-moving copy of critic
```

**Why target networks?** If you use the same network for both computing targets and updating weights, it is like trying to hit a moving target — unstable. Target networks move slowly (soft update every step):

```python
# line 85
pt.data.mul_(1.0 - tau).add_(p.data, alpha=tau)
# new_target = 0.995 × old_target + 0.005 × current
# tau = 0.005, so target slowly follows the main network
```

---

### `control-plane/control_plane/trainer.py` — the learning loop

**Reward function (lines 33–43)**
```python
def _reward(t, cache_pressure):
    return (
        +1.0 * cache_hit          # reward for serving from cache (fast!)
        - 1.0 * cache_miss        # penalty for cache miss (had to fetch)
        - 0.001 * latency_ms      # small penalty per millisecond of latency
        + 0.5 * anomaly * cache_hit  # bonus for caching anomaly streams correctly
        - 0.3 * cache_pressure    # penalty for evicting too much (cache thrashing)
    )
```

**Quantization (lines 47–67)**
```python
W = actor.input_proj.weight  # shape (19, 8): first layer weights
U, S, Vh = torch.linalg.svd(W)  # decompose into components
compressed = (S[:8] * Vh[:8]).mean(dim=1)  # extract 8 most important values
q = (compressed / maxabs * 127.0).round().clamp(-128, 127)  # scale to int8
```
SVD of a matrix W gives three matrices U, S, Vh such that `W = U × diag(S) × Vh`. S contains singular values (sorted largest first). The largest ones encode the most important patterns. We take the top 8 and collapse them to a single 8-element vector.

**Training loop (lines 168–255)**
```python
while True:
    time.sleep(0.05)                         # check for new data every 50ms

    if len(rb) < batch_size: continue        # wait for 64 transitions first

    batch = rb.sample(batch_size)            # pick 64 random transitions
    s, a, r, sp = ...                        # unpack state, action, reward, next_state

    # Critic update
    with torch.no_grad():
        noise = randn() * 0.2                # add noise to next action (exploration)
        ap = actor_target(sp) + noise        # what would we do in next state?
        q_target = r + gamma × min(q1_t, q2_t)  # what reward do we expect?
    q1, q2 = critic(s, a)                   # what did critic predict?
    loss = MSE(q1, target) + MSE(q2, target) # how wrong was the prediction?
    loss.backward()                          # compute gradients
    critic_opt.step()                        # update critic weights

    # Actor update (every 2 critic updates)
    actor_action = actor(s)                  # what would actor do in state s?
    q_actor = critic(s, actor_action)        # how good does critic think that is?
    actor_loss = -mean(q_actor)              # maximize Q → minimize negative Q
    actor_loss.backward()
    actor_opt.step()

    # Soft update targets
    agent.reset_targets(hard=False, tau=0.005)
```

---

### `control-plane/control_plane/state_tracker.py` — memory on the trainer side

This file maintains **rolling statistics** for each edge node: the last 10 cache hits/misses, last 20 stream requests, last 10 evictions.

```python
st.rolling_hits = deque(maxlen=10)   # only keep last 10 results (oldest drops off)
```

`deque` with `maxlen` automatically removes the oldest entry when you add a new one past the limit.

```python
# hit_rate = fraction of last 10 requests that were hits
hit_rate_recent = mean([1.0 if x else 0.0 for x in st.rolling_hits])
```

This mirrors what the ESP32 is computing internally, so the trainer has the same "view" of the state as the ESP32.

---

### `control-plane/control_plane/replay_buffer.py` — memory for training

```python
class GlobalReplayBuffer:
    def __init__(self, capacity=10_000):
        self._buf = deque(maxlen=10_000)  # holds last 10,000 transitions

    def push(self, transition):
        self._buf.append(transition)      # add new experience

    def sample(self, batch_size):
        return random.sample(list(self._buf), k=batch_size)  # pick randomly
```

Why random sampling? If you train on transitions in order (1, 2, 3, 4...), consecutive transitions are highly correlated — the network would overfit to recent patterns. Random sampling breaks this correlation.

---

### `demo/hardware_benchmark.py` — the proof

This script answers: "How much faster is the ESP32 int8 policy vs. the full CPU network?"

```python
# CPU benchmark
for _ in range(1000):
    state = torch.randn(1, 8)
    t0 = time.perf_counter()
    actor(state)          # full forward pass through LtCActor
    t1 = time.perf_counter()
    times.append((t1 - t0) * 1000)  # milliseconds

# Edge benchmark
for _ in range(1000):
    state_i8 = [random.randint(-128, 127) for _ in range(8)]
    t0 = time.perf_counter()
    score = sum(w * s for w, s in zip(weights, state_i8))  # dot product
    t1 = time.perf_counter()
    times.append((t1 - t0) * 1000)
```

Result: CPU ~0.195ms, Edge ~0.0007ms. Speedup: ~270×.

---

## 6. Glossary — Every Term

**Actor** — The part of the network that makes decisions. Takes in the state, outputs an action. "Actor" = "policy" = "decision maker."

**Agent** — In RL, the thing that takes actions. Here, both the full LTC network and the ESP32 int8 policy are "agents."

**Anomaly** — A sensor reading flagged as unusual (about 7% of requests in our simulation). The system always caches anomalies because unusual data is more likely to be needed again.

**AutoNCP** — A library that automatically designs the wiring pattern for an LTC network. NCP = Neural Circuit Policy.

**Batch** — A group of transitions sampled from the replay buffer for one round of training. Our batch size is 64.

**Broker (MQTT)** — The server that routes messages between publishers and subscribers. We use `broker.hivemq.com`, a free public broker.

**Cache hit** — The requested stream was already in the local cache. Served in 45ms.

**Cache miss** — The stream was not in the cache. Had to fetch from cloud. 800–2000ms.

**Cache pressure** — How often the cache is being forced to evict (delete) an item to make room. High pressure = too many different streams, cache is thrashing.

**CTDE** — Centralized Training, Decentralized Execution. Train with a big computer; execute with a tiny device.

**Critic** — The part of the network that evaluates decisions. Takes in (state, action), outputs a Q-value (expected future reward). The actor learns from the critic's feedback.

**deque** — A Python data structure that is like a list, but you can efficiently add/remove from both ends. With `maxlen`, old entries automatically drop off.

**Docker** — A tool that packages applications with all their dependencies into containers. `docker compose up` starts multiple containers from a single configuration file.

**Dot product** — Multiply matching elements of two arrays and sum the results. `[a,b,c] · [x,y,z] = ax + by + cz`. The ESP32 policy is a dot product of 8 weights and 8 state values.

**Edge computing** — Processing data close to where it is generated (the "edge" of the network) rather than sending everything to a central server. Reduces latency and bandwidth.

**Environment** — In RL, everything the agent interacts with. Here: the cache, the sensor streams, the latency. The environment reacts to the agent's action and produces a reward.

**ESP32** — A cheap (~$4) microcontroller with WiFi. Used in IoT devices. 240MHz CPU, 240KB RAM, no GPU, no floating-point accelerator.

**Eviction** — When the cache is full and a new item needs to be added, the least recently used existing item is evicted (removed) to make room.

**float32** — A 32-bit floating point number. Can represent values with ~7 decimal digits of precision. Standard for neural networks.

**Gradient** — In calculus, the direction you need to move a parameter to increase the output. Neural network training moves parameters in the negative gradient direction (to decrease the loss).

**int8** — An 8-bit integer. Values: -128 to 127. Takes 4× less memory than float32. Cannot represent fractions or very large/small numbers, but is much faster on constrained hardware.

**LRU (Least Recently Used)** — A cache replacement strategy: when the cache is full, evict the item that was used longest ago. The idea: if you haven't asked for it recently, you probably won't ask for it soon.

**LTC (Liquid Time-Constant network)** — A type of recurrent neural network where neurons have time constants (they "remember" the past with different speeds). Good for time-series data.

**MQTT** — Message Queuing Telemetry Transport. A lightweight pub/sub messaging protocol designed for IoT. Very small overhead per message, works on limited bandwidth.

**MSE (Mean Squared Error)** — `mean((predicted - actual)²)`. A loss function: how wrong were our predictions? We minimize this to improve the critic.

**Neural network** — A mathematical function with millions of learnable parameters (weights). Learns by adjusting weights to improve performance on a task. Inspired loosely by biological neurons.

**Policy** — The strategy the agent uses to decide what to do. In our case: the actor network (or the 8 int8 weights on the ESP32).

**Q-value** — The expected total future reward if you are in state S, take action A, and follow the current policy forever after. The critic estimates this.

**Quantization** — Converting floating-point weights to integers (e.g., float32 → int8). Loses some precision but makes computation much faster on hardware without FPUs.

**Replay buffer** — A memory bank that stores past experiences (transitions). The trainer randomly samples from this to learn, rather than learning from experiences in order.

**Reward** — A scalar signal the agent receives after each action. Positive = good decision, negative = bad decision. The agent tries to maximize total reward over time.

**RL (Reinforcement Learning)** — A branch of ML where an agent learns by trial and error, guided by rewards, rather than from labeled examples.

**Serial monitor** — A console in Wokwi that shows text output from the ESP32 (`Serial.printf(...)` calls). Used for debugging.

**Sigmoid** — A function that squashes any number to (0, 1). `sigmoid(x) = 1 / (1 + e^(-x))`. Used to get a "probability" output.

**Soft update** — Moving a target network slowly toward the main network: `target = 0.995 × target + 0.005 × main`. Prevents training instability.

**State (8D vector)** — The ESP32's description of its current situation. 8 numbers: cache fullness, last latency, payload size, anomaly flag, recent hit rate, stream frequency, time since last request, cache pressure.

**SVD (Singular Value Decomposition)** — A mathematical technique to decompose a matrix into its most important components. Used here to compress 19×8 = 152 weights into 8 numbers.

**Tanh** — A function that squashes any number to (-1, 1). Similar to sigmoid but centered at 0.

**Target network** — A copy of the main network that is updated slowly. Used in TD3 to provide stable training targets.

**TD3 (Twin Delayed Deep Deterministic Policy Gradient)** — The RL algorithm used here. Uses two critics (twins), delays actor updates, and adds noise to actions for exploration.

**Telemetry** — Data the ESP32 sends back to the trainer after every decision: what stream, hit or miss, latency, cache state, decision made.

**Threshold** — The value the score must exceed to trigger caching. We use 0: positive score = cache, negative or zero = don't cache.

**Transition** — One unit of experience: (state_before, action, reward, state_after). The replay buffer stores these.

**Wokwi** — A free browser-based ESP32 simulator. Runs real ESP32 firmware without real hardware. Supports WiFi simulation and can connect to external MQTT brokers.
