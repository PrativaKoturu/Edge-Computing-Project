# Dual Pipeline Testing & Monitoring

This folder contains tools for testing and monitoring both **edge-rl-oncloud** and **edge-rl-ondevice** pipelines simultaneously.

## 📁 Files

- **`app.py`** - Streamlit dashboard for real-time monitoring
- **`requirements.txt`** - Python dependencies for the dashboard

## 🚀 Quick Start

### Option 1: Run Test Suite (Automated)

```bash
# Install dependencies
pip install paho-mqtt

# Run the test (2 minutes)
python test_dual_pipeline.py
```

This will:
1. Start both Docker pipelines
2. Monitor MQTT messages
3. Collect latency data
4. Generate a comprehensive report
5. Save results to `test_results.json`

**Output:**
```
================================================================================
  DUAL PIPELINE TEST - Edge RL On-Cloud vs On-Device
================================================================================
Test Duration: 120 seconds
Start Time: 2026-04-15 10:30:45

📦 Starting oncloud pipeline...
✅ oncloud: Docker containers started
📦 Starting ondevice pipeline...
✅ ondevice: Docker containers started

🔌 Setting up MQTT monitoring for oncloud...
✅ oncloud: MQTT connected
🔌 Setting up MQTT monitoring for ondevice...
✅ ondevice: MQTT connected

⏳ Running test for 120 seconds...
[... messages flowing ...]

================================================================================
  TEST RESULTS
================================================================================

────────────────────────────────────────────────────────────────────────────────
  ONCLOUD
────────────────────────────────────────────────────────────────────────────────
  MQTT Connected:        ✅ Yes
  Requests Received:     150
  Telemetry Received:    150
  Policy Updates:        3

  Latency Statistics:
    Average:           45.23 ms
    Min:               42.10 ms
    Max:               67.89 ms
    Samples:           150

────────────────────────────────────────────────────────────────────────────────
  ONDEVICE
────────────────────────────────────────────────────────────────────────────────
  MQTT Connected:        ✅ Yes
  Requests Received:     150
  Telemetry Received:    150
  Policy Updates:        3

  Latency Statistics:
    Average:           42.15 ms
    Min:               39.20 ms
    Max:               58.45 ms
    Samples:           150

────────────────────────────────────────────────────────────────────────────────
  COMPARISON
────────────────────────────────────────────────────────────────────────────────
  On-Cloud Avg Latency:  45.23 ms
  On-Device Avg Latency: 42.15 ms
  Speedup:               1.07x

  On-Cloud Telemetry:    150 messages
  On-Device Telemetry:   150 messages
  Total:                 300 messages

✅ TEST PASSED: Both pipelines running successfully
✅ Results saved to: test_results.json
```

### Option 2: Run Dashboard (Interactive)

```bash
# Install dependencies
pip install -r dashboard/requirements.txt

# Start the dashboard
streamlit run dashboard/app.py
```

This opens a web interface at `http://localhost:8501` showing:

- **Real-time latency comparison** between pipelines
- **Cache hit rates** for both systems
- **Message flow statistics**
- **Latency distribution histograms**
- **Detailed metrics tables**
- **Recent telemetry logs**

---

## 🏗️ Test Architecture

### Both Pipelines Run Simultaneously

```
┌─────────────────────────────────────────────────────────────────┐
│              On-Cloud Pipeline (edge-rl-oncloud)                │
│  Docker Compose:                                                │
│  • MQTT Broker on port 11883                                    │
│  • Trainer + Traffic Generator                                  │
│  • Messages: edge/zone-a/* topics                               │
└─────────────────────────────────────────────────────────────────┘
          ↕
┌─────────────────────────────────────────────────────────────────┐
│              On-Device Pipeline (edge-rl-ondevice)              │
│  Docker Compose:                                                │
│  • MQTT Broker on port 1883                                     │
│  • Trainer + Traffic Generator + Wokwi (optional)               │
│  • Messages: edge/edge-rl-node/* topics                         │
└─────────────────────────────────────────────────────────────────┘
          ↕
┌─────────────────────────────────────────────────────────────────┐
│                   Test Monitor / Dashboard                       │
│  • Subscribes to both MQTT brokers                              │
│  • Collects latency, hit rate, message counts                   │
│  • Plots real-time metrics                                      │
└─────────────────────────────────────────────────────────────────┘
```

### Data Collection Points

1. **Requests Topic** (`edge/*/request`)
   - Traffic generator sends synthetic sensor requests
   - Tracked per pipeline

2. **Telemetry Topic** (`edge/*/telemetry`)
   - Edge node sends back decision + latency data
   - **Latency field extracted here** ← Main metric

3. **Policy Topic** (`edge/*/policy`)
   - Trainer sends updated RL policy weights
   - Counts policy updates over time

---

## 📊 Metrics Collected

### Per-Pipeline Metrics

| Metric | Description |
|--------|-------------|
| **MQTT Connected** | Whether MQTT client can reach broker |
| **Requests Received** | Number of requests from traffic generator |
| **Telemetry Received** | Number of responses from edge node |
| **Latency (avg, min, max)** | Request-response latency in ms |
| **Hit Rate** | % of cache hits in last N requests |
| **Policies Received** | Number of policy updates received |
| **Errors** | Any MQTT/JSON errors encountered |

### Comparative Metrics

| Metric | Description |
|--------|-------------|
| **Speedup** | On-Cloud Latency / On-Device Latency |
| **Total Messages** | Combined telemetry across both pipelines |
| **Hit Rate Difference** | On-Cloud rate - On-Device rate |

---

## 🔧 Configuration

### Test Duration

Edit in `test_dual_pipeline.py`:
```python
TEST_DURATION_SECONDS = 120  # 2 minutes
```

### MQTT Ports

- **On-Cloud**: `11883` (localhost)
- **On-Device**: `1883` (localhost)

Configured automatically, but can override in dashboard sidebar.

### Latency Recording

Latencies are automatically recorded from the `latency_ms` field in telemetry messages. The dashboard maintains a rolling window of 100 most recent latencies.

---

## 📈 Expected Results

### Normal Performance

- **On-Cloud**: 40–60 ms average latency (full network on GPU/CPU)
- **On-Device**: 35–50 ms average latency (int8 dot product on ESP32)
- **Speedup**: 1.0–1.5x (On-Cloud vs On-Device)
- **Hit Rate**: 45–65% initially, improving over time as policy learns
- **Message Count**: 100–200 messages per pipeline per minute

### Test Passing Criteria

✅ Both MQTT clients connect successfully  
✅ Requests are received on both pipelines  
✅ Telemetry data arrives with latency values  
✅ At least 50 telemetry messages per pipeline  
✅ No MQTT disconnects during test  
✅ Policy updates received on both sides  

### Test Failing Indicators

❌ MQTT connection fails  
❌ No messages received after 30 seconds  
❌ Telemetry missing latency_ms field  
❌ Docker containers exit unexpectedly  
❌ Broker unreachable errors  

---

## 🐛 Troubleshooting

### "MQTT connection failed"

**Cause:** Broker not running or wrong port  
**Fix:**
```bash
# Check if Docker containers are running
docker compose -f edge-rl-oncloud/docker-compose.yml ps
docker compose -f edge-rl-ondevice/docker-compose.yml ps

# Verify ports are open
netstat -an | grep 1883
netstat -an | grep 11883
```

### "No telemetry data arriving"

**Cause:** Pipelines not started or traffic generator not sending  
**Fix:**
```bash
# Check Docker logs
docker compose -f edge-rl-oncloud/docker-compose.yml logs -f traffic
docker compose -f edge-rl-ondevice/docker-compose.yml logs -f traffic
```

### "Dashboard shows no data"

**Cause:** MQTT client not connecting correctly  
**Fix:**
1. Click "Connect" button in sidebar
2. Check "On-Cloud" and "On-Device" status indicators turn green
3. Verify MQTT broker addresses/ports match your setup

### "ModuleNotFoundError: paho"

**Cause:** Missing dependencies  
**Fix:**
```bash
pip install paho-mqtt streamlit plotly pandas
```

---

## 📝 Results File

After test completion, results are saved to `test_results.json`:

```json
{
  "timestamp": "2026-04-15T10:30:45.123456",
  "duration_seconds": 120,
  "results": {
    "oncloud": {
      "mqtt_connected": true,
      "requests_received": 150,
      "telemetry_received": 150,
      "latencies": [45.2, 44.8, 46.1, ...],
      "hit_rate_avg": 0.52
    },
    "ondevice": {
      "mqtt_connected": true,
      "requests_received": 150,
      "telemetry_received": 150,
      "latencies": [42.1, 41.9, 43.2, ...],
      "hit_rate_avg": 0.58
    }
  },
  "latency_by_stream": {
    "oncloud": {...},
    "ondevice": {...}
  }
}
```

---

## 🎯 Next Steps

1. **Run test first**: `python test_dual_pipeline.py` (quick validation)
2. **Review results**: Open `test_results.json`
3. **Launch dashboard**: `streamlit run dashboard/app.py` (continuous monitoring)
4. **Analyze**: Compare latencies, hit rates, and policy learning curves

---

## 📧 Support

For issues or questions:
- Check Docker logs: `docker compose logs -f`
- Verify MQTT connectivity: `mosquitto_sub -h localhost -p 1883 -t "edge/#"`
- Review test results JSON file

---

**Last Updated:** April 15, 2026  
**Status:** ✅ Production Ready
