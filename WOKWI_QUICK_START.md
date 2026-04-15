# Wokwi Simulation - Quick Start Guide

Fast reference for running ESP32 simulations in VS Code.

---

## 🚀 2-Minute Setup

### Step 1: Install Wokwi Extension
```bash
# In VS Code Extensions marketplace, search and install:
# "Wokwi Simulator"
```

### Step 2: Start On-Cloud Simulation
```bash
cd edge-rl-oncloud/firmware
# Open in VS Code: code .
# Press: F1 → "Wokwi: Start Simulator"
# Wait for build and launch (first time: ~30 seconds)
```

### Step 3: Start On-Device Simulation (Optional)
```bash
# First, start Docker broker in another terminal:
cd edge-rl-ondevice
docker compose up -d

# Then start simulation:
cd edge-rl-ondevice/firmware
# Open in VS Code: code .
# Press: F1 → "Wokwi: Start Simulator"
```

---

## 📋 Configuration Reference

### On-Cloud (zone-a)
| Setting | Value |
|---------|-------|
| **Environment** | `zone-a` |
| **MQTT Broker** | `broker.hivemq.com:1883` |
| **Node ID** | `zone-a` |
| **Build Path** | `.pio/build/zone-a/` |
| **Hardware** | ESP32 + LCD (I2C) |
| **Purpose** | Centralized training |

### On-Device (edge-rl-node)
| Setting | Value |
|---------|-------|
| **Environment** | `edge-rl-node` |
| **MQTT Broker** | `localhost:1883` (Docker) |
| **Node ID** | `edge-rl-node` |
| **Build Path** | `.pio/build/edge-rl-node/` |
| **Hardware** | ESP32 + LED (GPIO 13) + Button (GPIO 12) |
| **Purpose** | On-device Q-learning |

---

## 🎮 Simulation Controls

### Wokwi Simulator Window

| Action | What It Does |
|--------|-------------|
| Click **Wokwi Terminal** tab | View ESP32 serial output (logs) |
| Press **GDB** (port 3333) | Debug with breakpoints |
| Click **Green LED** (on-device) | Visual indicator of cache hits |
| Click **Button** (on-device) | Manually trigger MQTT request |

### Keyboard Shortcuts
```
F1              Start Wokwi Simulator
F1 → "Wokwi"   Show all Wokwi commands
Ctrl+`          Toggle integrated terminal
```

---

## 📊 Expected Output

### On-Cloud Serial Log
```
[MQTT] Connecting to broker.hivemq.com:1883...
[MQTT] ✓ Connected to broker
[MQTT] ✓ Subscribed to edge/zone-a/request
[INFO] Waiting for requests...
[REQ] Received request: sensor-01/temperature
[POLICY] Policy update: 512 bytes
[INFO] Inference latency: 45.2ms
```

### On-Device Serial Log
```
[MQTT] Connecting to localhost:1883...
[MQTT] ✓ Connected to broker
[RL] Q-table initialized (256 states)
[REQ] Request: stream=cnc-01/vibration
[LEARN] Q[state][CACHE] += 0.045 (reward=+1.0)
[LED] ✓ Cache hit! LED ON
[LEARN] Epsilon: 0.890 → 0.889 (decay)
```

---

## 🔧 Troubleshooting

### "Firmware binary not found"
```bash
# Build manually:
cd firmware
pio build -e zone-a           # For on-cloud
pio build -e edge-rl-node     # For on-device

# Restart Wokwi
```

### "Cannot connect to MQTT"
```bash
# For on-cloud: broker.hivemq.com
# - Check internet connection
# - Firewall may block port 1883

# For on-device: localhost:1883 (Docker)
# - Verify Docker running: docker ps | grep mosquitto
# - Start broker: cd edge-rl-ondevice && docker compose up -d
```

### "Wokwi Terminal is empty"
```
- Click "Wokwi Terminal" tab (not VS Code Terminal)
- Check baud rate in serial output is 115200
- Restart: F1 → "Wokwi: Stop" → "Wokwi: Start"
```

### "Port 3333 already in use"
```bash
# Kill existing process
lsof -i :3333 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Retry Wokwi
```

---

## 📈 Monitoring Both Simultaneously

**Option 1: Split VS Code Windows** (Easiest)
```bash
# Terminal 1: On-Cloud
code edge-rl-oncloud/firmware
# F1 → Wokwi: Start

# Terminal 2: On-Device  
code edge-rl-ondevice/firmware
# F1 → Wokwi: Start
```

**Option 2: Dashboard** (Best visualization)
```bash
# With both pipelines running:
streamlit run dashboard/app.py

# Opens at: http://localhost:8501
# Shows latency comparison in real-time
```

---

## ✅ Checklist

Before starting simulations:
- [ ] Wokwi extension installed
- [ ] `pio --version` works
- [ ] Both `wokwi.toml` files exist
- [ ] Both `platformio.ini` files exist
- [ ] Can build: `pio build -e zone-a` and `pio build -e edge-rl-node`
- [ ] Docker installed (for on-device only)
- [ ] For on-device: Docker broker running

---

## 🎯 Next Steps

1. **Run both simulations** (see Quick Setup above)
2. **Open dashboard** for real-time monitoring:
   ```bash
   streamlit run dashboard/app.py
   ```
3. **Run automated tests** to validate:
   ```bash
   python3 test_dual_pipeline.py
   ```
4. **Review detailed guide** → [WOKWI_SETUP.md](WOKWI_SETUP.md)

---

**For detailed setup → [WOKWI_SETUP.md](WOKWI_SETUP.md)**  
**For testing & monitoring → [TESTING.md](TESTING.md)**
