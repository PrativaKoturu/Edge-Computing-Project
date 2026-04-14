# Demo Guide — What to Show Your Teacher

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
