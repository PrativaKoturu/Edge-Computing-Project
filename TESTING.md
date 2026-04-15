# Comprehensive Testing & Monitoring Guide

Complete guide for testing both **edge-rl-oncloud** and **edge-rl-ondevice** pipelines simultaneously.

---

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [Running Both Pipelines](#running-both-pipelines)
3. [Test Suite](#test-suite)
4. [Dashboard Monitoring](#dashboard-monitoring)
5. [Performance Analysis](#performance-analysis)
6. [Troubleshooting](#troubleshooting)

---

## 🚀 Quick Start

### One-Command Setup

```bash
# Start both pipelines
./start_dual_pipeline.sh

# In another terminal, start dashboard
./start_dual_pipeline.sh --with-dashboard

# Or run automated test
python3 test_dual_pipeline.py
```

That's it! Both pipelines will be running and collecting latency data.

---

## ⚙️ Running Both Pipelines

### Method 1: Using the Startup Script (Recommended)

```bash
# Start both pipelines
./start_dual_pipeline.sh

# Expected output:
# ✅ Docker containers started for on-cloud
# ✅ Docker containers started for on-device
# ✅ Both pipelines are running!
```

This automatically:
- Starts on-cloud on MQTT port **11883**
- Starts on-device on MQTT port **1883**
- Avoids port conflicts
- Sets up proper networking

### Method 2: Manual Docker Compose

**Terminal 1 — Start on-cloud:**
```bash
cd edge-rl-oncloud
docker compose up -d
docker compose logs -f
```

**Terminal 2 — Start on-device:**
```bash
cd edge-rl-ondevice
docker compose up -d
docker compose logs -f
```

### Verifying Both Are Running

```bash
# Check containers
docker ps

# Expected output:
# CONTAINER ID   IMAGE                    STATUS              NAMES
# abc123...      edge-computing...       Up 2 minutes        trainer-oncloud
# def456...      edge-computing...       Up 2 minutes        traffic-oncloud
# ghi789...      eclipse-mosquitto       Up 2 minutes        mosquitto-oncloud
# jkl012...      eclipse-mosquitto       Up 2 minutes        mosquitto-ondevice
# mno345...      edge-computing...       Up 2 minutes        traffic-ondevice

# Verify MQTT connectivity
mosquitto_sub -h localhost -p 11883 -t "edge/zone-a/telemetry" -v   # on-cloud
mosquitto_sub -h localhost -p 1883 -t "edge/edge-rl-node/telemetry" -v  # on-device
```

---

## 🧪 Test Suite

### Automated Testing (Recommended for Validation)

```bash
# Run the test (takes ~2 minutes)
python3 test_dual_pipeline.py
```

**What it does:**
1. Starts both pipelines
2. Connects MQTT clients to both brokers
3. Subscribes to all topics (requests, telemetry, policy)
4. Collects latency data for 120 seconds
5. Stops both pipelines
6. Generates comprehensive report
7. Saves results to `test_results.json`

**Output Example:**
```
================================================================================
  DUAL PIPELINE TEST - Edge RL On-Cloud vs On-Device
================================================================================

✅ on-cloud: MQTT connected
✅ on-device: MQTT connected

⏳ Running test for 120 seconds...
📤 on-cloud: Request #1 - cnc-01/vibration
📥 on-cloud: Telemetry #1 - cnc-01/vibration (latency=45ms, hit=False)
📥 on-device: Telemetry #1 - cnc-15/pressure (latency=42ms, hit=True)
...

================================================================================
  TEST RESULTS
================================================================================

On-Cloud:
  • Requests: 150
  • Telemetry: 150
  • Policies: 3
  • Avg Latency: 45.23 ms (min: 42.10, max: 67.89)

On-Device:
  • Requests: 150
  • Telemetry: 150
  • Policies: 3
  • Avg Latency: 42.15 ms (min: 39.20, max: 58.45)

Comparison:
  • Speedup: 1.07x
  • Total Messages: 300
  • Both pipelines healthy: ✅ YES

✅ Results saved to: test_results.json
```

### Test Results File

After testing, review `test_results.json`:

```json
{
  "timestamp": "2026-04-15T10:30:45.123456",
  "duration_seconds": 120,
  "results": {
    "oncloud": {
      "mqtt_connected": true,
      "requests_received": 150,
      "telemetry_received": 150,
      "policy_received": 3,
      "latencies": [45.2, 44.8, 46.1, 43.2, ...],
      "hit_rate_avg": 0.52,
      "errors": []
    },
    "ondevice": {
      "mqtt_connected": true,
      "requests_received": 150,
      "telemetry_received": 150,
      "policy_received": 3,
      "latencies": [42.1, 41.9, 43.2, 40.8, ...],
      "hit_rate_avg": 0.58,
      "errors": []
    }
  },
  "latency_by_stream": {
    "oncloud": {
      "cnc-01/vibration": [45.1, 45.3, 45.2],
      "cnc-02/temperature": [44.8, 43.9, 44.5],
      ...
    },
    "ondevice": {
      "cnc-15/pressure": [42.1, 41.9, 42.0],
      ...
    }
  }
}
```

---

## 📊 Dashboard Monitoring

### Starting the Dashboard

```bash
# Start both pipelines first
./start_dual_pipeline.sh

# In another terminal
streamlit run dashboard/app.py
```

Opens dashboard at: **http://localhost:8501**

### Dashboard Features

#### 🎯 Top Metrics Row
- **On-Cloud Avg Latency** - Real-time average
- **On-Device Avg Latency** - Real-time average
- **On-Cloud Telemetry** - Message count
- **On-Device Telemetry** - Message count

#### 📈 Latency Over Time Chart
- Line plot showing every latency measurement
- Compare both pipelines side-by-side
- Interactive tooltips with exact values
- Identifies latency spikes

#### 🎯 Hit Rate Comparison
- Bar chart: cache hit % for last 20 requests
- Shows learning progress
- On-cloud vs on-device comparison

#### 📊 Latency Distribution
- Histogram showing latency buckets
- Overlaid for both pipelines
- Helps identify typical vs outlier latencies

#### 📥 Detailed Metrics Tables
- Per-pipeline breakdown
- Min, max, average latency
- Total message counts
- Policy update tracking

#### 📋 Recent Telemetry Tabs
- View last 10 telemetry messages
- Stream ID, latency, cache status
- Sortable, searchable tables

### Dashboard Controls

**Sidebar Options:**
- **MQTT Broker** - Hostname for each pipeline (default: localhost)
- **MQTT Port** - Port numbers (on-cloud: 11883, on-device: 1883)
- **Connect Button** - Reconnect to brokers
- **Refresh Interval** - Dashboard update frequency (1-10 seconds)
- **Status Indicators** - Green = connected, Red = disconnected

---

## 📈 Performance Analysis

### Understanding the Results

#### Expected Latency Ranges

| Pipeline | Typical Range | Notes |
|----------|---------------|-------|
| **On-Cloud** | 40–70 ms | Full network on CPU/GPU |
| **On-Device** | 35–60 ms | int8 dot product on ESP32 |

**Why similar?**
- Both have network overhead (MQTT request/response)
- Both have inference time (but on-device is ~270× faster)
- Total latency dominated by network round-trip, not compute

#### Cache Hit Rate Interpretation

- **Initial (0–5 min)**: ~40–50% (random policy)
- **Learning (5–15 min)**: ~50–70% (policy improving)
- **Mature (15+ min)**: ~70–85% (learned policy optimal)

The trainer (on-cloud) updates the policy every 200 critic steps (~2-3 minutes).

#### Message Flow Metrics

| Metric | Expected | Interpretation |
|--------|----------|-----------------|
| **Requests** | 100–200 per 2 min | Traffic generator running |
| **Telemetry** | ~equal to requests | Edge responding to requests |
| **Policies** | 1–3 per 2 min | Trainer updating weights |

### Comparative Analysis

#### Speedup Calculation

```
Speedup = On-Cloud Latency / On-Device Latency

Typical results:
  • Speedup 0.9–1.2x means similar performance
  • Both have network overhead
  • On-device inference is faster but outweighed by network
  • This is EXPECTED and CORRECT
```

#### Real Performance Bottleneck

The 270× speedup shows up when measuring **pure inference time**:

```python
# On-cloud: Full neural network
On-Cloud CPU Time:   ~0.19 ms
On-Cloud GPU Time:   ~0.02 ms

# On-device: int8 dot product
On-Device Time:      ~0.0007 ms (0.7 µs)

Speedup:             270×
```

But in a real system with MQTT latency:
```
Total Latency = Network RTT + Inference Time
              ≈ 45 ms + 0.0007 ms  (on-device)
              ≈ 45 ms + 0.0002 ms  (on-cloud GPU)

Since network dominates, total latency is similar.
```

---

## 🔍 Detailed Monitoring

### Watching Trainer Learn

**Terminal:**
```bash
docker compose -f edge-rl-oncloud/docker-compose.yml logs -f trainer
```

**Look for:**
- `critic_loss` decreasing (model learning)
- `updates=200` → policy pushed to edge
- `replay_size` growing (collecting experience)

```
INFO trainer: Replay size=100  latest hit=False lat=1523ms
INFO trainer: updates=50   critic_loss=0.3421  actor_loss=-0.0123
INFO trainer: updates=100  critic_loss=0.2145  actor_loss=-0.0089
INFO trainer: updates=150  critic_loss=0.1234  actor_loss=-0.0067
INFO trainer: updates=200  critic_loss=0.0821  actor_loss=-0.0045  🎯 POLICY PUSHED
```

### Watching Traffic Generator

**Terminal:**
```bash
docker compose -f edge-rl-ondevice/docker-compose.yml logs -f traffic
```

**Look for:**
- `Burst #N sent X requests` every 30 seconds
- `Anomaly rate in dataset: 3.39%`
- `Dataset X% complete`

```
INFO traffic: Burst #1 sent 20 requests (anomalies=0) | dataset 0.2% complete
INFO traffic: Burst #2 sent 20 requests (anomalies=1) | dataset 0.4% complete
```

### Watching Edge Node Receive Messages

**Terminal (if running Wokwi):**
```bash
# In VS Code, click "Wokwi Terminal" tab
# Watch for:
[req] stream=cnc-01/vibration cache=5
[learn] action=CACHE reward=+0.5 td_err=+0.12 eps=0.45
[policy] updated int8 weights from trainer
```

---

## 🐛 Troubleshooting

### "Both pipelines won't start"

**Check Docker:**
```bash
docker ps -a  # See all containers
docker logs <container_name>  # View error logs
```

**Fix:**
```bash
# Clean up old containers
docker compose -f edge-rl-oncloud/docker-compose.yml down
docker compose -f edge-rl-ondevice/docker-compose.yml down

# Try again
./start_dual_pipeline.sh
```

### "No telemetry arriving"

**Cause 1: Traffic generator not running**
```bash
docker logs traffic-oncloud
docker logs traffic-ondevice
# Look for error messages
```

**Cause 2: MQTT broker not accessible**
```bash
# Test connectivity
mosquitto_pub -h localhost -p 11883 -t "test" -m "hello"
mosquitto_pub -h localhost -p 1883 -t "test" -m "hello"
# Should succeed with no errors
```

**Fix:**
```bash
docker compose -f edge-rl-oncloud/docker-compose.yml restart mosquitto
docker compose -f edge-rl-ondevice/docker-compose.yml restart mosquitto
```

### "Dashboard shows no data"

**Step 1: Verify brokers are running**
```bash
docker ps | grep mosquitto
# Should see both mosquitto-oncloud and mosquitto-ondevice
```

**Step 2: Click "Connect" button in dashboard sidebar**

**Step 3: Check status indicators turn green**

**Step 4: If still empty, restart dashboard**
```bash
streamlit run dashboard/app.py
```

### "Latency values look wrong"

**Check what's being recorded:**
```bash
mosquitto_sub -h localhost -p 1883 -t "edge/edge-rl-node/telemetry" -v | head -5
# Look at latency_ms field
```

**If missing:**
- Edge code not sending telemetry properly
- Check firmware/main.cpp has telemetry publishing code

### "Port 1883 already in use"

**Find what's using it:**
```bash
lsof -i :1883
# Kill if necessary
kill -9 <PID>
```

**Or use different port:**
```bash
# Edit edge-rl-ondevice/docker-compose.yml
# Change: ports: - "1883:1883"
# To:     ports: - "1884:1883"
```

---

## 📊 Performance Tips

### For Better Latency Measurements

1. **Reduce network latency variance:**
   - Run Docker on same machine as test
   - Use localhost MQTT connections
   - Avoid other network-heavy applications

2. **Collect more samples:**
   - Increase `TEST_DURATION_SECONDS` in test script
   - Default is 120s (120 samples typical)
   - Use 300s (5 min) for more stable averages

3. **Monitor streaming in dashboard:**
   - Keep dashboard open during full test
   - Watch metrics stabilize over time
   - Hit rate should increase as policy learns

---

## 📝 Reporting Results

### Key Metrics to Report

```
Test Date: 2026-04-15
Duration: 120 seconds
System: 2 pipelines running simultaneously

On-Cloud Results:
- MQTT Connectivity: ✅ Stable
- Telemetry Messages: 150
- Avg Latency: 45.23 ms
- Min/Max: 42.10 / 67.89 ms
- Cache Hit Rate: 52%
- Policy Updates: 3

On-Device Results:
- MQTT Connectivity: ✅ Stable
- Telemetry Messages: 150
- Avg Latency: 42.15 ms
- Min/Max: 39.20 / 58.45 ms
- Cache Hit Rate: 58%
- Policy Updates: 3

Conclusion:
- Both pipelines stable ✅
- Similar latency (network-dominated) ✅
- Edge learning from trainer ✅
- Ready for production ✅
```

---

## 🎓 Learning Resources

### Understand the Data Flow

1. **Request → Response Cycle** (Dashboard → Latency)
2. **Policy Learning** (Trainer → Policy Updates)
3. **Cache Optimization** (Hit Rate Improvement)

See main README.md for detailed architecture explanation.

### Modifying the Test

Edit `test_dual_pipeline.py` to:
- Change test duration: `TEST_DURATION_SECONDS = 300`
- Change MQTT ports: `MQTT_PORT_ONCLOUD = 11883`
- Add new metrics: Edit `test_results` dict

---

## 📧 Support

For issues:
1. Check [Troubleshooting](#troubleshooting) section
2. Review Docker logs: `docker compose logs`
3. Check MQTT connectivity: `mosquitto_sub`
4. Verify data format: Look at `test_results.json`

---

**Last Updated:** April 15, 2026  
**Status:** ✅ Production Ready  
**License:** MIT
