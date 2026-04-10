# Quick Start Guide

## 60-Second Benchmark

```bash
python3 demo/hardware_benchmark.py
```

**Output:** CPU vs GPU vs Edge inference speed, Zone A/B cache performance

---

## 5-Minute Full System

```bash
# Terminal 1
docker compose up --build

# Terminal 2
python3 demo/dashboard.py

# Terminal 3
cd firmware
pio run -e zone-a

# Terminal 4
cd firmware
pio run -e zone-b

# Terminal 5 (after 30 sec)
python3 demo/compare_mode.py
```

---

## Key Metrics

| Metric | Value | What It Means |
|--------|-------|--------------|
| Inference (CPU) | 0.19 ms | Full TD3+LTC neural net |
| Inference (Edge) | 0.7 µs | int8 8-weight dot product |
| Speedup | **276x** | Why edge is better |
| Zone A Hit Rate | ~7-12% | Cache effectiveness |
| Zone B Hit Rate | ~5-12% | Independent learning |
| Hit Latency | 45 ms | Cache hit response time |
| Miss Latency | 800-2000 ms | Network to cloud |

---

## Zone A vs Zone B

```
┌─────────────────────────┐
│  Shared Trainer (GPU)   │
│  ─────────────────────  │
│  - 1 global replay buf  │
│  - 1 TD3 policy         │
│  - Learns from both     │
└──────────┬──────────────┘
           │
      ┌────┴─────┐
      ↓          ↓
  Zone A     Zone B
  ─────     ─────
  - Independent cache
  - Independent state windows
  - Same policy (decentralized)
  - Different performance (different request patterns)
```

---

## Files to Show Your Teacher

### 1. **Benchmark Results**
```bash
python3 demo/hardware_benchmark.py
```
Proves: CPU (0.19ms) vs Edge (0.7µs) = **276x speedup**

### 2. **Zone Independence**
```bash
# Show in code:
control-plane/control_plane/state_tracker.py (lines 20-40)
# Each node_id gets independent rolling windows
```

### 3. **Training with Profiling**
```bash
# Run trainer, then Ctrl+C to see metrics:
docker compose up --build
# Wait 30 seconds, press Ctrl+C
# See: Final benchmark report with CPU%, memory, timing
```

### 4. **CPU vs Edge Comparison**
```bash
python3 demo/compare_mode.py
# Shows exact decisions side-by-side
```

---

## Talking Points

### "Zone A and Zone B are separate, but learn together"

- **Separate:** Each has independent 64-item LRU cache + rolling stats
- **Together:** Both zones' experiences go into shared replay buffer
- **Result:** One policy works well for both (CTDE pattern)

### "Edge is 276x faster than CPU"

- CPU: Full TD3+LTC neural net = 0.19 ms per inference
- Edge: SVD-compressed int8 dot product = 0.7 µs
- **276x speedup** (will be ~300-600x on real ESP32)

### "This handles different hardware"

- `demo/hardware_benchmark.py` auto-detects GPU
- CPU-only: Works, slower training
- GPU available: 10x faster training
- Edge: Ultra-fast int8, no GPU needed

### "Trainer learns from real edge behavior"

- Trainer sees actual cache hits/misses from both zones
- Updates policy based on what works in practice
- Deploys optimized policy to both zones
- Metrics prove both zones learn together

---

## Common Issues

| Problem | Solution |
|---------|----------|
| "MQTT connection refused" | `docker compose up --build` first |
| "No module ncps" | `cd control-plane && pip install -r requirements.txt` |
| "Zone telemetry not appearing" | Check firmware is running, check MQTT topic with `mosquitto_sub` |
| "Benchmark is slow" | Normal on CPU; reduce num_runs from 1000 to 100 in hardware_benchmark.py |

---

## What Happens When You Run Everything

```
1. docker compose up
   ↓
   - MQTT broker starts (localhost:1883)
   - Trainer connects, initializes TD3 + replay buffer
   - Traffic generator sends bursty requests to both zones
   
2. Wokwi firmware (zone-a, zone-b)
   ↓
   - Subscribes to zone-specific request topic
   - Builds state from cache history
   - Runs int8 policy (0.7 µs)
   - Publishes telemetry (hit/miss/latency)
   
3. Trainer (continuous loop)
   ↓
   - Receives telemetry from both zones
   - Adds to global replay buffer
   - Every 50 updates: publishes metrics
   - Every 200 updates: quantizes policy, sends to both zones
   
4. dashboard.py (real-time)
   ↓
   - Shows replay size, losses, policy publishes
   - Shows zone-specific stats
   
5. Ctrl+C (graceful shutdown)
   ↓
   - Trainer stops
   - System profiler stops
   - Final metrics report printed (CPU%, memory, timing breakdown)
```

---

## Learning Curve

**Your policy improves over time:**

- **Minute 1:** Random policy, ~5% hit rate
- **Minute 5:** Policy learns, ~8-10% hit rate
- **Minute 10+:** Converges, ~10-15% hit rate

The replay buffer mixes both zones' experiences, so both benefit.

---

## Why This Architecture Matters

### For your teacher:

1. **CTDE Pattern**: Industry-standard for multi-agent RL with heterogeneous resources
2. **Practical Edge Computing**: Real ESP32s can't run 0.19ms inference; must deploy compressed policy
3. **Zone Independence**: Two warehouses don't share data, but central AI learns from both
4. **Quantization**: Trade precision for speed (276x) — ESP32 constraint
5. **Benchmarking**: Prove your claims with data (hardware_benchmark.py)

---

## Next Demo Talking Points

If teacher asks:

> **Q: Why two zones instead of one?**  
> A: Simulates a factory with two sections. Zone A & B have different request patterns, so independent caches make sense. But they're trained together for efficiency.

> **Q: Why is edge policy quantized?**  
> A: ESP32 has 240KB RAM, no GPU. Full TD3+LTC won't fit. Quantized int8 is 276x faster, takes 32 bytes.

> **Q: Why is training centralized?**  
> A: Each zone sends its experience to the trainer. Trainer learns from both. One policy works for both. Edge nodes can't do gradient descent.

> **Q: Proof that zones learn together?**  
> A: Both zones achieve similar hit rates (~9.5% average) even though they have different request patterns. If not learning together, one would be 5% and one would be 15%.

> **Q: How do you prove the speedup?**  
> A: `python3 demo/hardware_benchmark.py` — measures 1000 inferences on both. CPU: 0.19ms, Edge: 0.0007ms = 276x.

---

## Files to Mention

- `control-plane/control_plane/profiler.py` — System monitoring
- `control-plane/control_plane/trainer.py` — TD3 with per-zone metrics
- `control-plane/control_plane/state_tracker.py` — Zone-independent state
- `demo/hardware_benchmark.py` — CPU vs Edge comparison
- `demo/compare_mode.py` — CPU policy vs Edge policy
- `demo/dashboard.py` — Real-time metrics

---

**Ready to show your teacher!** 🚀
