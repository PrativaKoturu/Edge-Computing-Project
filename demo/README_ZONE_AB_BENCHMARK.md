# Zone A/B Edge Computing Benchmark

Complete guide to running the MARL edge caching system with Zone A/B architecture, benchmarking, and hardware comparison.

## What You'll See

This benchmark demonstrates:

1. **Zone A & B Architecture**: Two geographically separated edge nodes with independent caches, trained centrally with shared experience
2. **Hardware Comparison**: CPU vs GPU vs Edge (int8 quantized) inference performance
3. **Performance Metrics**: Hit rates, latency, throughput, and per-zone statistics
4. **Real-time Dashboard**: Live training metrics and zone performance

---

## Quick Start (5 minutes)

### 1. Hardware Benchmark Only

Test inference speed on your machine without full system:

```bash
python3 demo/hardware_benchmark.py
```

**What you'll see:**
- CPU TD3+LTC inference time (~0.2 ms)
- GPU TD3+LTC inference time (if available)
- Edge int8 inference time (~0.7 µs) — **260-300x faster!**
- Zone A vs Zone B caching performance
- Tradeoff analysis: quantization quality vs speed

---

## Full System (Real-time Training)

### 2. Start Control Plane (Trainer + Traffic)

```bash
docker compose up --build
```

This starts:
- **MQTT Broker** on localhost:1883
- **TD3 Trainer** (with GPU support if available)
- **Traffic Generator** (bursty 50+ CNC machines)

Metrics are published to `trainer/stats` topic every 50 updates.

### 3. Run Dashboard (in another terminal)

```bash
python3 demo/dashboard.py
```

**Live metrics:**
- Replay buffer size
- Critic/actor loss
- Policy update count
- Per-zone request/hit stats
- Training throughput

### 4. Simulated Edge Nodes (Zone A & B)

In the Wokwi simulator or using the CLI:

```bash
# Terminal 1: Zone A
cd firmware
pio run -e zone-a

# Terminal 2: Zone B
pio run -e zone-b
```

Each node:
- Subscribes to `edge/{zone_id}/request`
- Publishes `edge/{zone_id}/telemetry`
- Listens for policy updates on `edge/{zone_id}/policy`
- Maintains independent int8 cache state

### 5. Compare Mode

After trainer has run for a bit (once replay buffer has 500+ samples):

```bash
python3 demo/compare_mode.py
```

**Shows:**
- CPU policy decisions vs Edge policy decisions
- Hit rates and latency for both
- Decision delta (|a_cpu - a_edge|)
- Which policy makes better cache decisions

---

## Architecture: Zone A & Zone B

```
┌─────────────────────────────────────────────────────────┐
│  CONTROL PLANE (Centralized Training)                   │
│  ─────────────────────────────────────────────────────  │
│  TD3 Trainer (CPU or GPU)                               │
│  - Global replay buffer (shared experience)              │
│  - Actor/Critic networks                                │
│  - Policy quantization every N updates                   │
│  - Per-zone state tracking                               │
└─────────────────────────────────────────────────────────┘
         │                           │
    ┌────┴─────┐               ┌─────┴─────┐
    │  ZONE A   │               │  ZONE B   │
    └────┬─────┘               └─────┬─────┘
         │ (independent          │ (independent
         │  cache state)         │  cache state)
         │                       │
    ┌────┴─────────┬─────────────┴─────┐
    │              │                   │
  Request      Policy                Telemetry
   (MQTT)       (int8)               (MQTT)
    │              │                   │
    ↓              ↓                   ↓
┌──────────────────────────────────────────┐
│  ESP32 Edge Node (Wokwi Simulator)       │
│  ─────────────────────────────────────── │
│  - Int8 8-weight dot-product inference   │
│  - 64-item LRU cache                     │
│  - Rolling window stats                  │
│  - Anomaly detection                     │
└──────────────────────────────────────────┘
```

### State Tracking (Per Zone)

Each zone maintains independent rolling windows:

- **Cache hits** (last 10 requests)
- **Stream frequencies** (last 20 requests)
- **Cache evictions** (last 10)
- **Time since last request**

This ensures Zone A's high-frequency streams don't bias Zone B's cache decisions.

---

## Key Metrics

### Zone Metrics (Per Telemetry)

```
- node_id: zone-a or zone-b
- cache_hit: boolean
- latency_ms: 45 (hit) or 800-2000 (miss)
- cache_items: current occupancy
- payload_kb: request size
- score_int32: int8 policy output
```

### Trainer Metrics (Per 50 Updates)

```
- replay_size: transitions in buffer
- critic_updates: total critic updates so far
- critic_loss_avg10: rolling 10-step average
- actor_loss_avg10: rolling 10-step average
- policy_publishes: how many times we've quantized and sent policy
```

### System Profiler (Background)

The trainer automatically collects:

```python
# Per operation (ms)
timing_buckets = {
    "inference": list[float],        # actor forward pass
    "critic_update": list[float],    # critic loss → backward
    "actor_update": list[float],     # actor loss → backward
}

# System-wide
{
    "cpu_mean_percent": float,
    "cpu_max_percent": float,
    "memory_mean_mb": float,
    "memory_max_mb": float,
}
```

---

## Performance Baseline

### Inference Speed (1000 runs)

| Policy | Mean | Min | Max | Speedup |
|--------|------|-----|-----|---------|
| CPU TD3+LTC | 0.19 ms | 0.17 ms | 6.1 ms | 1x |
| GPU TD3+LTC | ~0.02 ms* | — | — | ~10x* |
| Edge int8 | 0.0007 ms | 0.0006 ms | 0.005 ms | **276x** |

*GPU speedup varies (requires CUDA)

### Zone Hit Rate Parity

Both zones achieve similar hit rates when trained together:

- Zone A: ~7-12% cache hit rate
- Zone B: ~5-12% cache hit rate
- Variation due to independent request patterns (not because of CTDE)

### Latency Reduction (Edge vs CPU Policy)

Average request latency (100 requests):

- Zone A: 1263 → 1247 ms (-16 ms)
- Zone B: 1343 → 1354 ms (+11 ms)

**Note:** Latency variance is dominated by network/cloud fetch time (800-2000 ms), not policy quality. The real win is the **276x faster inference** on ESP32.

---

## Comparing Against Your Machine

The hardware benchmark adapts to your system:

```bash
python3 demo/hardware_benchmark.py
```

- **No GPU**: Reports CPU-only inference
- **With GPU**: Compares CPU vs GPU vs Edge
- **Shows device info**: cores, memory, PyTorch version
- **Estimates**: power, thermal, suitability for edge deployment

---

## Modifying Zone Configuration

To change zone count, update:

**docker-compose.yml:**
```yaml
environment:
  EDGE_NODE_IDS: "zone-a,zone-b,zone-c"  # Add zone-c
  BURST_PERIOD_S: "15"                     # Faster bursts
  BURST_MIN_KB: "300"                      # Smaller payloads
```

**PlatformIO (firmware):**
```ini
[env:zone-c]
build_flags = -DZONE_ID=\"zone-c\"
```

The trainer and state tracker automatically scale to any number of zones.

---

## Troubleshooting

### "MQTT connection refused"
```bash
# Make sure docker is running and MQTT container is up
docker compose logs mqtt
```

### "ModuleNotFoundError: ncps"
```bash
cd control-plane
pip install -r requirements.txt
```

### Hardware benchmark runs slowly
The benchmark does 1000 forward passes. On slow machines, reduce to 100:

```python
# In hardware_benchmark.py, change:
cpu_result = benchmark_cpu_policy(actor, num_runs=100)  # was 1000
```

### Zone telemetry not appearing
Check firmware is running and publishing to correct topic:
```bash
docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry"
```

---

## Next Steps

1. **Longer training** (5+ min): Hit rates improve as policy learns
2. **More zones**: Change `EDGE_NODE_IDS` and add firmware variants
3. **Custom workloads**: Modify traffic generator to match your factory
4. **Real ESP32s**: Compile firmware and deploy to Wokwi/real hardware
5. **GPU training**: Install CUDA and uncomment GPU path in trainer

---

## Papers & References

- **CTDE (Centralized Training, Decentralized Execution)**: Common in MARL for heterogeneous agents
- **TD3**: Twin Delayed DDPG for continuous control (Fujimoto et al., 2018)
- **LTC (Liquid Time-Constant Networks)**: Neural ODE approximation for embedded inference
- **Quantization**: int8 SVD-based compression for edge deployment

---

## Questions?

Check the inline docs:
- `control_plane/trainer.py` — TD3 training loop with profiling
- `control_plane/models.py` — LTC actor and TD3 critic
- `control_plane/state_tracker.py` — Per-zone state building
- `demo/compare_mode.py` — CPU vs Edge policy comparison
- `demo/hardware_benchmark.py` — Hardware profiling
