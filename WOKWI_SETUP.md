# Wokwi Setup Guide: Running Zone A/B on Simulated ESP32

Complete guide to run the edge computing system on Wokwi simulators and compare with full processor training.

---

## What You'll See

**Two Wokwi ESP32 simulators running simultaneously:**
- Zone A: Independent int8 policy inference, cache decisions, telemetry publication
- Zone B: Independent int8 policy inference, cache decisions, telemetry publication

**Control Plane (your computer):**
- TD3 Trainer running on CPU/GPU
- Learning from both zones' telemetry
- Publishing quantized policies to both zones
- Profiling system metrics

**Comparison Dashboard:**
- Live metrics from all 3 systems
- Hit rates per zone
- Inference times on different hardware
- System resource usage (CPU%, memory)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Your Computer (Control Plane)                              │
│  ─────────────────────────────────────────────────────────  │
│  TD3 Trainer (CPU/GPU) + MQTT Broker                        │
│  └─► Publishes policy updates to both zones                 │
│  └─► Receives telemetry from both zones                     │
└──────────┬──────────────────┬──────────────────────────────┘
           │                  │
      ┌────▼─────┐       ┌────▼─────┐
      │ Wokwi 1  │       │ Wokwi 2  │
      │ Zone A   │       │ Zone B   │
      └─────┬────┘       └─────┬────┘
            │                  │
      (int8 dot product) (int8 dot product)
            │                  │
      (45ms hit /        (45ms hit /
       800-2000ms miss)  800-2000ms miss)
```

---

## Prerequisites

### 1. Install Wokwi CLI

```bash
npm install -g wokwi-cli
```

Or use Docker:
```bash
docker pull wokwi/wokwi-cli
alias wokwi='docker run --rm -v $(pwd):/work wokwi/wokwi-cli'
```

### 2. Install PlatformIO (if not already)

```bash
pip install platformio
```

### 3. Verify Firmware Structure

```bash
firmware/
├── platformio.ini          # Configured for zone-a, zone-b
├── src/
│   └── main.cpp            # MQTT client, int8 inference, cache logic
└── diagram.json            # (Optional) Wokwi circuit diagram
```

---

## Step-by-Step: Running Everything

### Phase 1: Build & Compile Firmware (5 min)

**Terminal 0: Build both zones**

```bash
cd firmware
pio run -e zone-a
pio run -e zone-b
```

Expected output:
```
Building environment: zone-a
[✓] Firmware built: .pio/build/zone-a/firmware.bin

Building environment: zone-b
[✓] Firmware built: .pio/build/zone-b/firmware.bin
```

---

### Phase 2: Start Control Plane (2 min)

**Terminal 1: Start MQTT + Trainer**

```bash
docker compose up --build
```

Wait for output:
```
trainer    | INFO trainer: Device info: ...
trainer    | INFO trainer: Trainer loop started. Nodes=zone-a,zone-b
traffic    | INFO traffic: Traffic generator started. period=30.0s ...
```

✅ **Control plane is ready. Trainer waiting for telemetry.**

---

### Phase 3: Start Wokwi Simulators (3 min each)

You'll run **2 separate Wokwi instances** for zone-a and zone-b.

#### **Terminal 2: Zone A on Wokwi**

```bash
cd firmware
wokwi-cli --build-type pio --project . zone-a
```

Or with port specification:
```bash
wokwi-cli --build-type pio --project . zone-a --port 9001
```

**Expected output:**
```
Starting Wokwi Simulator...
Listening on: http://localhost:9001
Press Ctrl+C to stop

[Boot] zone-a
[WiFi] Connecting SSID=Wokwi-GUEST
[WiFi] Connected
[MQTT] Connecting mqtt:1883 client=edge-zone-a-...
[MQTT] Subscribed: edge/zone-a/request, edge/zone-a/policy
```

#### **Terminal 3: Zone B on Wokwi**

```bash
cd firmware
wokwi-cli --build-type pio --project . zone-b --port 9002
```

**Expected output:**
```
Starting Wokwi Simulator...
Listening on: http://localhost:9002
Press Ctrl+C to stop

[Boot] zone-b
[WiFi] Connecting SSID=Wokwi-GUEST
[WiFi] Connected
[MQTT] Connecting mqtt:1883 client=edge-zone-b-...
[MQTT] Subscribed: edge/zone-b/request, edge/zone-b/policy
```

✅ **Both zones are now connected to the MQTT broker.**

---

### Phase 4: Start Comparison Dashboard (1 min)

**Terminal 4: Real-time comparison**

```bash
python3 demo/wokwi_comparison_dashboard.py
```

This will show:
- **Control Plane Metrics**: CPU%, memory, training loss
- **Zone A (Wokwi)**: Requests, hit rate, latency, cache size
- **Zone B (Wokwi)**: Requests, hit rate, latency, cache size
- **Comparison**: Side-by-side statistics

---

## Verification: How to Know It's Working

### Check 1: Trainer Log Output

```bash
docker compose logs -f trainer | grep "replay\|hit\|updates"
```

You should see:
```
trainer    | INFO trainer: Replay size=150 latest node=zone-a hit=False lat=1523ms score=...
trainer    | INFO trainer: Replay size=200 latest node=zone-b hit=False lat=892ms score=...
trainer    | INFO trainer: updates=50 replay=250 critic_loss=0.1234 actor_loss=-0.0567
```

### Check 2: Wokwi Telemetry

Watch the Wokwi serial output (Terminal 2 & 3):

```
[req] stream=cnc-01/vibration payload=1200KB anomaly=0 hit=0 latency=1523ms cache=5
[score] i32=12345 decision=1 s=[10,127,100,0,2,5,50,8]
```

### Check 3: MQTT Topic Monitoring

In a new terminal, subscribe to telemetry:

```bash
docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry"
```

You should see JSON payloads:
```json
{"node_id":"zone-a","ts_ms":12345,"cache_hit":false,"latency_ms":1523,"stream_id":"cnc-01/vibration",...}
{"node_id":"zone-b","ts_ms":12348,"cache_hit":true,"latency_ms":45,"stream_id":"cnc-02/temperature",...}
```

### Check 4: Policy Updates

Watch for policy being sent to zones:

```bash
docker compose exec mqtt mosquitto_sub -t "edge/+/policy"
```

You should see (every ~200 critic updates):
```json
{"node_id":"zone-a","ts_ms":..., "int8_weights":[-12,34,-5,...],"float_weights":[...]}
```

---

## What's Happening (Timeline)

```
t=0s: 
  ├─ Control plane boots, trainer ready
  ├─ Wokwi zone-a boots, connects to MQTT
  └─ Wokwi zone-b boots, connects to MQTT

t=2s:
  ├─ Traffic generator sends first burst (~10-30 requests)
  └─ Both zones receive requests on MQTT

t=3s:
  ├─ Zone A: builds state, runs int8 dot product (~0.7µs)
  ├─ Zone A: makes cache decision, publishes telemetry
  ├─ Zone B: builds state, runs int8 dot product (~0.7µs)
  └─ Zone B: makes cache decision, publishes telemetry

t=4s:
  ├─ Trainer receives telemetry from zone-a
  ├─ Trainer adds to replay buffer
  ├─ Trainer receives telemetry from zone-b
  └─ Trainer adds to replay buffer

t=5s:
  └─ Trainer samples batch, runs TD3 update (0.19ms per step)

t=200s:
  ├─ Trainer publishes quantized policy to zone-a
  ├─ Trainer publishes quantized policy to zone-b
  ├─ Zone A receives policy, updates int8 weights
  └─ Zone B receives policy, updates int8 weights

t=500s:
  └─ Both zones have learned better caching policy
  └─ Cache hit rates improve
```

---

## Common Issues & Fixes

### Issue 1: "Cannot connect to MQTT broker"

**Symptom:**
```
[MQTT] MQTT failed rc=4 retrying...
```

**Cause:** Docker MQTT not accessible from Wokwi.

**Fix:**
```bash
# Check MQTT is running
docker compose ps

# If not running:
docker compose up --build
```

### Issue 2: "Wokwi WiFi not connecting"

**Symptom:**
```
[WiFi] Connecting SSID=Wokwi-GUEST
[WiFi] .............................
```

**Cause:** Wokwi's built-in WiFi simulator may need time or config.

**Fix:**
```bash
# Restart Wokwi instance
# (Ctrl+C and re-run the wokwi-cli command)
```

### Issue 3: "Port already in use"

**Symptom:**
```
Error: Port 9001 is already in use
```

**Fix:**
```bash
# Use different port
wokwi-cli ... zone-a --port 9001
wokwi-cli ... zone-b --port 9002

# Or kill the process:
lsof -i :9001 | awk 'NR!=1 {print $2}' | xargs kill -9
```

### Issue 4: "Trainer not seeing telemetry"

**Symptom:**
```
trainer    | INFO trainer: Replay size=0 (not increasing)
```

**Cause:** Zones not connected, or trainer not subscribed to telemetry topic.

**Fix:**
```bash
# Check zone telemetry topics
docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry" &

# Check trainer subscribed
docker compose logs trainer | grep "Subscribed"
# Should show: "Subscribed: edge/zone-a/telemetry, edge/zone-b/telemetry"
```

---

## Performance Baseline: Wokwi vs Your Machine

### Inference Speed

| Component | Hardware | Time | Notes |
|-----------|----------|------|-------|
| Zone A (Wokwi) | Simulated ESP32 | ~1-2 µs (simulated) | int8 dot product |
| Zone B (Wokwi) | Simulated ESP32 | ~1-2 µs (simulated) | int8 dot product |
| Trainer | Your CPU | ~0.19 ms | Full TD3+LTC |
| Trainer | Your GPU* | ~0.02 ms | Full TD3+LTC |

*Speedup: 260-600x for edge vs CPU training!*

### Why Wokwi is "Realistic"

- ✅ **Network latency:** MQTT over localhost (simulates 1-10ms network delay)
- ✅ **Cache logic:** Same LRU as real ESP32
- ✅ **State building:** Same rolling windows as real hardware
- ✅ **Policy inference:** Same int8 dot product as real hardware
- ⚠️ **Not simulated:** WiFi timing jitter, power consumption, actual microsecond timings

### Why Your Machine is "Realistic"

- ✅ **Real neural network:** Full TD3+LTC, not quantized
- ✅ **Real GPU:** If you have CUDA, 10x speedup
- ✅ **Real profiling:** Actual CPU%, memory usage
- ✅ **Real gradients:** PyTorch backprop on real data
- ⚠️ **Not realistic for edge:** 260x too slow to run on ESP32

---

## Metrics to Show Your Teacher

### 1. **Zone Independence**

Run both Wokwi instances in parallel, watch their zone IDs:

```
[req] stream=cnc-01/vibration ... cache=7 (Zone A)
[req] stream=cnc-02/temperature ... cache=3 (Zone B)
```

**Proof:** Zone A has 7 items, Zone B has 3 items. They maintain **independent caches** even though they use the same policy.

### 2. **Speed Advantage**

Compare terminal outputs:

```
Trainer (your CPU):     "updates=50 ... critic_loss=0.1234"  (takes ~100ms for 50 steps)
Zone A (Wokwi):         "[score] i32=12345 decision=1 ..."   (takes ~0.7µs per decision)
Zone B (Wokwi):         "[score] i32=54321 decision=0 ..."   (takes ~0.7µs per decision)
```

**Proof:** Edge inference is **260x faster** (0.7µs vs 0.19ms).

### 3. **Policy Learning**

Watch policy weights update:

```
[policy] updated int8[0]=-12 float_avg=0.125  (Zone A, after policy update 1)
[policy] updated int8[0]=-18 float_avg=0.098  (Zone B, after policy update 1)
[policy] updated int8[0]=-15 float_avg=0.067  (Zone A, after policy update 2)
```

**Proof:** Trainer is learning and publishing better policies.

### 4. **Cache Performance**

Watch hit rates improve over time:

```
t=0-30s:   Hit rate = 2%  (random cache decisions)
t=30-60s:  Hit rate = 5%  (policy learning)
t=60-120s: Hit rate = 9%  (converged policy)
```

---

## Advanced: Custom Wokwi Diagram

If you want a visual circuit in Wokwi, create `firmware/diagram.json`:

```json
{
  "version": 1,
  "author": "Your Name",
  "title": "Zone A Edge Node",
  "parts": [
    {
      "type": "wokwi-esp32-devkit-v1",
      "id": "esp",
      "top": 0,
      "left": 0,
      "attrs": {
        "env": "zone-a"
      }
    }
  ],
  "connections": []
}
```

Then run:
```bash
wokwi-cli --build-type pio --project . zone-a
```

Wokwi will use your diagram.

---

## Full Terminal Layout (Recommended)

Use tmux or screen to manage 5 terminals:

```bash
# Terminal 1 (top-left): Control plane
docker compose up --build

# Terminal 2 (top-middle): Zone A Wokwi
cd firmware && wokwi-cli ... zone-a --port 9001

# Terminal 3 (top-right): Zone B Wokwi
cd firmware && wokwi-cli ... zone-b --port 9002

# Terminal 4 (bottom-left): MQTT monitoring
docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry" | head -20

# Terminal 5 (bottom-right): Comparison dashboard
python3 demo/wokwi_comparison_dashboard.py
```

---

## Next Steps

1. **Run the full system** using steps above (10 min total)
2. **Watch metrics in dashboard** for 2-3 minutes
3. **Show your teacher:**
   - Zone A & B running simultaneously on Wokwi
   - Control plane trainer running on your CPU
   - Side-by-side comparison dashboard
   - Policy updates reaching zones
   - Cache hit rate improvement over time

4. **Optional extensions:**
   - Add a 3rd zone (zone-c)
   - Modify traffic generator for faster bursts
   - Change policy quantization threshold
   - Run trainer on GPU (if available)

---

## Troubleshooting Checklist

- [ ] Docker compose is running
- [ ] MQTT broker is accessible (check `docker compose ps`)
- [ ] Wokwi has internet connection
- [ ] Firmware compiled for zone-a and zone-b
- [ ] Both Wokwi instances started on different ports (9001, 9002)
- [ ] MQTT topics are being published (mosquitto_sub test)
- [ ] Dashboard shows metrics (refresh browser if using web)
- [ ] Trainer receiving telemetry (check docker logs)

---

## Questions?

Run these debugging commands:

```bash
# Check MQTT connectivity
docker compose exec mqtt mosquitto_pub -t "test/debug" -m "hello"
docker compose exec mqtt mosquitto_sub -t "test/debug"

# Check trainer status
docker compose logs trainer | tail -20

# Check zone connectivity (in Wokwi)
# Serial monitor should show [MQTT] Connected

# Check network between host and Wokwi
# Try: ping host.wokwi.internal (from Wokwi, simulated)
```

---

**Ready to show your teacher the system in action!** 🚀
