# Wokwi ESP32 Simulation Setup Guide

Complete guide for simulating both **edge-rl-oncloud** and **edge-rl-ondevice** ESP32 nodes in Wokwi.

---

## 📋 Table of Contents

1. [Installation](#installation)
2. [Architecture Overview](#architecture-overview)
3. [On-Cloud Setup](#on-cloud-setup)
4. [On-Device Setup](#on-device-setup)
5. [Running Simulations](#running-simulations)
6. [Monitoring Simulation](#monitoring-simulation)
7. [Troubleshooting](#troubleshooting)

---

## 🔧 Installation

### Prerequisites

1. **VS Code** (Latest version)
2. **Wokwi for VS Code Extension** - Install from VS Code marketplace
3. **PlatformIO Extension** - For building firmware
4. **Docker** - For running broker and trainer services

### Install Wokwi Extension

In VS Code:
```
Extensions → Search "Wokwi" → Install "Wokwi Simulator"
```

Or command line:
```bash
code --install-extension wokwi.wokwi-simulator
```

### Verify Installation

```bash
# Check PlatformIO CLI is available
pio --version

# Check you can build firmware
cd edge-rl-ondevice/firmware
pio build -e edge-rl-node
```

---

## 🏗️ Architecture Overview

### Simulation Stack

```
┌─────────────────────────────────────────────────────────┐
│            VS Code with Wokwi Extension                 │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Wokwi Simulator (Browser-based in editor pane)  │  │
│  │                                                  │  │
│  │  ┌────────────────────────────────────────────┐ │  │
│  │  │  ESP32 Simulation (ARM cortex-M4 emulated) │ │  │
│  │  │  - Running compiled firmware (.bin/.elf)   │ │  │
│  │  │  - Serial output to terminal               │ │  │
│  │  │  - Network access (localhost via bridge)   │ │  │
│  │  └────────────────────────────────────────────┘ │  │
│  │  - LED (GPIO 13) - visual activity indicator   │  │
│  │  - Button (GPIO 12) - manual control           │  │
│  └──────────────────────────────────────────────────┘  │
│                        │                                │
│ ┌──────────────────────▼─────────────────────────────┐ │
│ │         Serial Monitor (115200 baud)               │ │
│ │ Shows real-time logs from ESP32 firmware           │ │
│ └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
           │
           │ Network (MQTT over localhost)
           ▼
┌─────────────────────────────────────────────────────────┐
│              Docker (Running on Host)                    │
│                                                          │
│  Broker (Mosquitto)  ←→  Trainer (Python)               │
│  Port: 1883/11883        (Running inference)            │
└─────────────────────────────────────────────────────────┘
```

### Key Components

| Component | Role | Location |
|-----------|------|----------|
| **wokwi.toml** | Configuration for Wokwi simulator | `firmware/` |
| **diagram.json** | Virtual circuit connections | `firmware/` |
| **platformio.ini** | Build settings and MQTT config | `firmware/` |
| **main.cpp** | ESP32 firmware code | `firmware/src/` |
| **.pio/build** | Compiled firmware output | Auto-generated |

---

## ☁️ On-Cloud Setup

### File Locations

```
edge-rl-oncloud/firmware/
├── wokwi.toml          ✅ Configured
├── diagram.json        ✅ Configured
├── platformio.ini      ✅ Configured
└── src/
    └── main.cpp        ✅ Firmware code
```

### Configuration Details

**wokwi.toml:**
```toml
[wokwi]
version = 1
firmware = ".pio/build/zone-a/firmware.bin"
elf = ".pio/build/zone-a/firmware.elf"
gdbServerPort = 3333

[[wokwi.uart]]
index = 0
baud = 115200

[[wokwi.network]]
host = "broker.hivemq.com"    # Cloud MQTT broker
port = 1883
```

**diagram.json:**
- ESP32 Dev Kit V1 (main board)
- 16×2 LCD Display (I2C connection on GPIO 21/22)
- Visual feedback of control plane activity

**platformio.ini:**
```ini
[env:zone-a]
platform = espressif32
board = esp32dev
framework = arduino
monitor_speed = 115200
lib_deps =
  knolleary/PubSubClient@^2.8
  bblanchon/ArduinoJson@^7.0.4
build_flags =
  -DNODE_ID='"zone-a"'
  -DMQTT_HOST='"broker.hivemq.com"'
  -DMQTT_PORT=1883
```

### Starting On-Cloud Simulation

**Step 1: Open folder in VS Code**
```bash
code edge-rl-oncloud/firmware
```

**Step 2: Start Wokwi simulation**
- Click the Wokwi icon in the bottom status bar
- Or: `F1` → Type "Wokwi: Start Simulator"

**Step 3: Build firmware automatically**
- Wokwi will build if needed
- Watch terminal for build output

**Step 4: Observe simulation**
- ESP32 boots and connects to broker
- LCD shows connection status
- Serial monitor shows detailed logs

**Expected Output:**
```
[MQTT] Connecting to broker.hivemq.com:1883...
[MQTT] Connected! Subscribing to topics...
[LCD] Ready: 0 updates
[MSG] Request received: sensor-01/temperature
[POLICY] Policy update received (64 bytes)
...
```

---

## 🖥️ On-Device Setup

### File Locations

```
edge-rl-ondevice/firmware/
├── wokwi.toml          ✅ Configured
├── diagram.json        ✅ Configured (ENHANCED)
├── platformio.ini      ✅ Configured
└── src/
    └── main.cpp        ✅ Firmware code
```

### Configuration Details

**wokwi.toml:**
```toml
[wokwi]
version = 1
firmware = ".pio/build/edge-rl-node/firmware.bin"
elf = ".pio/build/edge-rl-node/firmware.elf"
gdbServerPort = 3333

[wokwi.simulation]
speed = "1MHz"                 # Slower for on-device Q-learning

[[wokwi.uart]]
index = 0
baud = 115200

[[wokwi.network]]
host = "localhost"             # Local Docker MQTT broker
port = 1883
```

**diagram.json (UPDATED):**
- ESP32 Dev Kit V1 (main edge node)
- **Green LED** (GPIO 13) - Lights up on cache hit
- **Push Button** (GPIO 12) - Manual trigger for requests
- Serial monitor for real-time logs

**platformio.ini:**
```ini
[env:edge-rl-node]
platform = espressif32
board = esp32dev
framework = arduino
monitor_speed = 115200
lib_deps =
  knolleary/PubSubClient@^2.8
  bblanchon/ArduinoJson@^7.0.4
build_flags =
  -DNODE_ID='"edge-rl-node"'
  -DMQTT_HOST='"localhost"'    # Connects to Docker broker
  -DMQTT_PORT=1883
```

### Starting On-Device Simulation

**Step 1: Ensure Docker services are running**
```bash
cd edge-rl-ondevice
docker compose up -d
```

**Step 2: Open folder in VS Code**
```bash
code edge-rl-ondevice/firmware
```

**Step 3: Start Wokwi simulation**
- Click the Wokwi icon in bottom status bar
- Or: `F1` → "Wokwi: Start Simulator"

**Step 4: Observe simulation**
- ESP32 boots and connects to localhost MQTT
- Green LED flashes on cache hits
- Serial monitor shows Q-learning progress
- Press button to manually trigger requests

**Expected Output:**
```
[MQTT] Connecting to localhost:1883...
[MQTT] Connected! Subscribing to topics...
[RL] Q-table initialized (256 states × 10 actions)
[REQ] Request #1: stream=cnc-01/vibration q_max=0.123
[LEARN] action=CACHE reward=+1.0 td_error=0.045 eps=0.890
[LED] Cache HIT! (GPIO 13 lights)
...
```

---

## ▶️ Running Simulations

### Run Both Simultaneously

**Option 1: Two VS Code Windows (Easiest)**

Terminal 1 - On-Cloud:
```bash
code edge-rl-oncloud/firmware
# Click Wokwi icon to start simulator
```

Terminal 2 - On-Device:
```bash
# First start Docker services
cd edge-rl-ondevice
docker compose up -d

# Then open firmware in VS Code
code edge-rl-ondevice/firmware
# Click Wokwi icon to start simulator
```

**Option 2: Using start_dual_pipeline.sh**

```bash
# Start Docker services for both (optional, only needed for on-device)
./start_dual_pipeline.sh

# Then manually open simulators in VS Code
code edge-rl-oncloud/firmware
code edge-rl-ondevice/firmware
```

### Simulation Controls

#### On-Cloud Simulator
- **Serial Monitor Tab**: View all logs
- **GDB Debugger**: Set breakpoints (port 3333)
- **LCD Display**: Watch system status

#### On-Device Simulator
- **Green LED**: Blinks on cache hits
- **Push Button**: Click to trigger request
- **Serial Monitor**: Watch Q-learning training
- **GDB Debugger**: Debug on-device learning

---

## 📊 Monitoring Simulation

### Serial Monitor Output

**On-Cloud (Centralized Training):**
```
[INFO] 10:30:45.123 | MQTT Connected
[INFO] 10:30:46.456 | Policy update: 512 bytes received
[INFO] 10:30:47.789 | Processing request: cnc-01/vibration
[INFO] 10:30:48.012 | Sending inference: {model_id: "v4.2", size: 64}
[INFO] 10:30:48.234 | Response: {prediction: 0.845, latency: 123ms}
[DEBUG] Batch processor: collected 50 samples, loss=0.234
```

**On-Device (Local Q-Learning):**
```
[INFO] 10:30:45.123 | MQTT Connected
[INFO] 10:30:46.456 | Q-table ready: 256 states
[INFO] 10:30:47.789 | Request received: cnc-15/pressure
[INFO] 10:30:48.012 | Q-learning: q_max=0.342 action=CACHE
[INFO] 10:30:48.234 | Cache HIT! reward=+1.0, TD_error=0.045
[DEBUG] Epsilon decay: 0.890 → 0.889
```

### Dashboard Integration

While simulations run, monitor via dashboard:
```bash
streamlit run dashboard/app.py
```

Dashboard shows:
- Real-time latency from both simulations
- Cache hit rates (on-device)
- Policy updates (on-cloud)
- Message flow in real-time

### Checking Broker Connection

```bash
# Verify on-cloud can reach public broker
mosquitto_pub -h broker.hivemq.com -p 1883 -t "test" -m "hello"

# Verify on-device reaches Docker broker
mosquitto_pub -h localhost -p 1883 -t "test" -m "hello"

# Subscribe to see messages
mosquitto_sub -h localhost -p 1883 -t "edge/+/telemetry" -v
```

---

## 🐛 Troubleshooting

### Wokwi Won't Start

**Error: "Cannot find firmware binary"**
```
Solution:
1. Build manually: cd firmware && pio build -e edge-rl-node
2. Check .pio/build exists
3. Restart VS Code
4. Try again: F1 → Wokwi: Start Simulator
```

**Error: "Port 3333 already in use"**
```bash
# Kill existing process
lsof -i :3333 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Try again
```

### Serial Monitor Not Showing

**Issue: No output in Wokwi terminal**
```
Solution:
1. Click "Wokwi Terminal" tab (not "Terminal" tab)
2. If still empty, restart: F1 → Wokwi: Stop Simulator
3. Then F1 → Wokwi: Start Simulator
4. Check baud rate is 115200
```

### MQTT Connection Failed (On-Cloud)

**Error: "Cannot connect to broker.hivemq.com"**
```
Causes:
- Firewall blocking port 1883
- Network connection issue
- Broker is down

Solution:
1. Verify you can ping broker: ping broker.hivemq.com
2. Test manually: mosquitto_pub -h broker.hivemq.com -t test -m hi
3. If blocked, edit MQTT_HOST in platformio.ini to use localhost
   (need to run local Mosquitto in Docker)
```

### MQTT Connection Failed (On-Device)

**Error: "Cannot connect to localhost:1883"**
```
Causes:
- Docker broker not running
- Wokwi can't reach Docker network

Solution:
1. Verify broker is running: docker ps | grep mosquitto
2. If not: cd edge-rl-ondevice && docker compose up -d
3. Check broker logs: docker logs mosquitto-ondevice
4. Restart Wokwi: Stop → Start
```

### Simulation Too Slow

**Symptom: Everything takes too long, freezes**
```
Causes:
- CPU throttling
- Simulation speed set too low
- GDB debugger attached

Solution:
1. Check wokwi.toml simulation speed:
   [wokwi.simulation]
   speed = "1MHz"     ← Change to "full" if too slow
2. Detach debugger if attached
3. Close other applications
```

### LED Not Blinking (On-Device)

**Symptom: Green LED doesn't respond**
```
Causes:
- main.cpp not wired to GPIO 13
- diagram.json not configured

Solution:
1. Check diagram.json has LED on GPIO 13
2. Verify main.cpp: digitalWrite(13, HIGH/LOW)
3. Restart simulation
```

---

## 🎓 Best Practices

### Simulation Timing

**On-Cloud:**
- Simulates full inference pipeline
- Includes network round-trip
- Expected: 40–70 ms latency

**On-Device:**
- Simulates Q-learning on 256-state table
- Inference is ~0.7 µs (fast!)
- Expected: Similar total latency due to network

### Debugging Strategy

1. **Check Serial Output First**
   - Is it connecting to MQTT?
   - Are requests being received?
   - Any error messages?

2. **Monitor MQTT Messages**
   ```bash
   mosquitto_sub -h localhost -p 1883 -t "edge/+/telemetry" -v
   ```

3. **Use Dashboard**
   - Real-time visualization
   - Compare both pipelines
   - Spot latency issues

4. **Enable GDB if Needed**
   - Attach debugger to port 3333
   - Set breakpoints in main.cpp
   - Step through critical sections

### Performance Profiling

To measure pure inference time (excluding network):

**On-Device:**
```cpp
// In main.cpp
auto start = micros();
// ... q_learning inference ...
auto elapsed = micros() - start;
Serial.printf("[PERF] Q-learning: %lu µs\n", elapsed);
```

**On-Cloud:**
```cpp
// In main.cpp
auto start = micros();
// ... send request & wait response ...
auto elapsed = micros() - start;
Serial.printf("[PERF] Network round-trip: %lu µs\n", elapsed);
```

---

## 📚 Resources

### Wokwi Documentation
- [Wokwi Documentation](https://docs.wokwi.com)
- [Wokwi for VS Code](https://docs.wokwi.com/vscode)
- [ESP32 Pins Reference](https://docs.wokwi.com/parts/board-esp32-devkit-v1)

### PlatformIO
- [PlatformIO Docs](https://docs.platformio.org)
- [ESP32 Board Support](https://docs.platformio.org/en/latest/boards/espressif32/esp32dev.html)

### MQTT in Arduino
- [PubSubClient Library](https://github.com/knolleary/pubsubclient)
- [Arduino JSON Library](https://github.com/bblanchon/ArduinoJson)

---

## ✅ Verification Checklist

Before running simulations, verify:

- [ ] Wokwi extension installed in VS Code
- [ ] PlatformIO CLI available (`pio --version`)
- [ ] Both `wokwi.toml` files have correct paths
- [ ] Both `diagram.json` files are valid JSON
- [ ] Docker installed (for on-device)
- [ ] Mosquitto available for testing (`mosquitto_pub`)
- [ ] Can build firmware: `pio build -e edge-rl-node`
- [ ] For on-device: Docker broker running (`docker compose up -d`)

Once all checked, simulations are ready to run! 🚀

---

## 🆘 Support

For issues:
1. Check Wokwi terminal output (not VS Code terminal)
2. Review error messages for path or network issues
3. Test MQTT connectivity separately
4. Consult [Troubleshooting](#troubleshooting) section above

**Last Updated:** April 15, 2026  
**Status:** ✅ Verified & Working  
**License:** MIT
