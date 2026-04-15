# 🔧 Wokwi Serial Monitor - Troubleshooting Guide

**Problem:** No logs appearing in Wokwi simulator

This guide walks through the most common issues and fixes.

---

## 🎯 Quick Checklist (Try These First!)

- [ ] **Click "Wokwi Terminal" tab** (NOT "Terminal" tab)
- [ ] **Simulator is running** (check status bar icon)
- [ ] **Build completed successfully** (check terminal for "BUILD SUCCESSFUL")
- [ ] **Wait 3-5 seconds** after simulator starts
- [ ] **Restart simulator** (F1 → "Wokwi: Stop Simulator", then Start again)

**If still nothing?** → Continue to Step 1 below

---

## 📋 Step-by-Step Troubleshooting

### Step 1: Verify Wokwi is Actually Running

**What to check:**
1. Look at bottom VS Code status bar (right side)
2. Should show a Wokwi icon with status

**If you see:**
- ✅ Green icon "Wokwi Simulator Running" → Proceed to Step 2
- ❌ No icon or red icon → Simulator not running

**To fix:**
```bash
# In VS Code, press F1 and type:
"Wokwi: Start Simulator"

# Wait 10-15 seconds for build + launch
# Watch terminal for: "Wokwi simulator started"
```

---

### Step 2: Check You're Looking at the Right Tab

**This is the #1 mistake!**

In the Wokwi simulator window (appears in editor pane):

```
┌─────────────────────────────────────┐
│ ⚙️ Wokwi Simulator                  │
├─────────────────────────────────────┤
│ [Board] [Serial] [GDB]              │  ← Tabs at top
├─────────────────────────────────────┤
│                                     │
│  (Your simulator view here)         │
│                                     │
│  Output console below:              │
│  [Wokwi Terminal] [Terminal]        │  ← These are bottom tabs
│  [View output here] ← YOUR LOGS     │
└─────────────────────────────────────┘
```

**What to do:**
1. Look for tabs at the **bottom** of the Wokwi window
2. Click **"Wokwi Terminal"** tab (not "Terminal" tab)
3. Logs should appear there

If you still see nothing, proceed to Step 3.

---

### Step 3: Verify Serial Baud Rate

**Check wokwi.toml has correct baud rate:**

**For on-cloud** (`edge-rl-oncloud/firmware/wokwi.toml`):
```toml
[[wokwi.uart]]
index = 0
baud = 115200          ✅ Correct
```

**For on-device** (`edge-rl-ondevice/firmware/wokwi.toml`):
```toml
[[wokwi.uart]]
index = 0
baud = 115200          ✅ Correct
```

**Both should have `baud = 115200`**

If different:
```bash
# Edit the file and fix it
nano edge-rl-oncloud/firmware/wokwi.toml   # or on-device
# Change baud to: 115200
# Save (Ctrl+O, Enter, Ctrl+X)

# Restart simulator: F1 → Stop, then Start
```

---

### Step 4: Check Serial.begin() is in setup()

**Verify firmware calls Serial.begin()**

Run this command:
```bash
grep -n "Serial.begin" edge-rl-oncloud/firmware/src/main.cpp
grep -n "Serial.begin" edge-rl-ondevice/firmware/src/main.cpp
```

**Should output:**
```
edge-rl-oncloud/firmware/src/main.cpp:237:  Serial.begin(115200);
edge-rl-ondevice/firmware/src/main.cpp:370:    Serial.begin(115200);
```

✅ Both files have it → Proceed to Step 5

❌ One or both missing → Need to add it:

**Add this to main.cpp setup() function (near beginning):**
```cpp
void setup() {
  Serial.begin(115200);      // ← ADD THIS LINE
  delay(1000);               // Wait for serial to initialize
  Serial.println("System booting...");
  
  // ... rest of setup code ...
}
```

---

### Step 5: Rebuild Firmware and Restart

**Clean rebuild:**
```bash
# For on-cloud:
cd edge-rl-oncloud/firmware
pio clean -e zone-a
pio build -e zone-a

# For on-device:
cd edge-rl-ondevice/firmware
pio clean -e edge-rl-node
pio build -e edge-rl-node
```

**Check for:**
- ✅ `Building...` messages
- ✅ `BUILD SUCCESSFUL` at end
- ❌ `error:` messages (if so, check main.cpp syntax)

**Then restart Wokwi:**
```bash
# In VS Code: F1 → "Wokwi: Stop Simulator"
# Wait 2 seconds
# Then: F1 → "Wokwi: Start Simulator"
```

**Wait 5-10 seconds** for boot messages to appear.

---

### Step 6: Check WiFi Connection

Wokwi needs to connect to WiFi before doing much.

**Look for these messages in serial output:**
```
Attempting WiFi connection...
Connected to WiFi! IP: 192.168.X.X
```

If you see nothing, there may be an issue with WiFi or MQTT setup.

**Add debug logging to check:**

Edit `edge-rl-ondevice/firmware/src/main.cpp` (or on-cloud):

Find the `setup()` function and add at the very beginning:
```cpp
void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n\n=== SYSTEM BOOTING ===");
  Serial.print("Node ID: ");
  Serial.println(NODE_ID);
  Serial.print("MQTT Host: ");
  Serial.println(MQTT_HOST);
  Serial.print("MQTT Port: ");
  Serial.println(MQTT_PORT);
  Serial.println("Attempting WiFi connection...");
  
  // ... rest of code ...
}
```

Then rebuild and restart simulator. You should see boot messages immediately.

---

### Step 7: Check MQTT Connection Logs

After WiFi connects, the code should try MQTT.

**Look for these messages:**
```
Attempting WiFi connection...
Connected to WiFi! IP: 192.168.4.1
Connecting to MQTT broker...
MQTT connected!
```

**If you see "MQTT connected!" → Logs are working!**

**If you see "MQTT connection failed" → Check:**
1. Is MQTT broker running? (For on-device: `docker ps | grep mosquitto`)
2. Is MQTT host correct in platformio.ini?

---

## 🔍 Advanced Debugging

### Verify diagram.json Has Serial Configured

**Check that serial output is enabled:**

**For on-cloud** (`edge-rl-oncloud/firmware/diagram.json`):
```json
{
  "version": 1,
  "author": "Prativa Koturu",
  "editor": "wokwi",
  "title": "Edge Computing RL Control Plane",
  "parts": [
    {
      "type": "board-esp32-devkit-v1",
      "id": "esp32",
      ...
    },
    ...
  ],
  "connections": [...],
  "serial": [
    {
      "type": "serial",
      "target": "esp32"
    }
  ]              ← Serial config should be here
}
```

**For on-device** (`edge-rl-ondevice/firmware/diagram.json`):
```json
{
  ...
  "serial": [
    {
      "type": "serial",
      "target": "esp32"
    }
  ]              ← Serial config should be here
}
```

✅ Both should have the `"serial"` section

If missing, add it:
```json
  "serial": [
    {
      "type": "serial",
      "target": "esp32"
    }
  ]
```

---

### Force Wokwi Cache Clear

Sometimes Wokwi caches old firmware:

```bash
# On macOS:
rm -rf ~/.wokwi ~/.wokwi-cache

# Then in VS Code: F1 → "Wokwi: Stop Simulator"
# Then: F1 → "Wokwi: Start Simulator"
```

---

### Check Wokwi Extension Version

In VS Code:
1. Go to Extensions (Ctrl+Shift+X)
2. Search for "Wokwi"
3. Check version (should be latest)
4. If outdated, click "Update"
5. Restart VS Code

---

## 📝 Complete Debugging Checklist

Use this if none of the above work:

```bash
# 1. Verify Wokwi extension installed
code --list-extensions | grep -i wokwi

# 2. Check both wokwi.toml files exist
ls -la edge-rl-oncloud/firmware/wokwi.toml
ls -la edge-rl-ondevice/firmware/wokwi.toml

# 3. Check both diagram.json files exist and are valid JSON
cat edge-rl-oncloud/firmware/diagram.json | python3 -m json.tool
cat edge-rl-ondevice/firmware/diagram.json | python3 -m json.tool

# 4. Check Serial.begin in both main.cpp files
grep "Serial.begin" edge-rl-oncloud/firmware/src/main.cpp
grep "Serial.begin" edge-rl-ondevice/firmware/src/main.cpp

# 5. Rebuild both
cd edge-rl-oncloud/firmware && pio clean && pio build -e zone-a
cd ../../../edge-rl-ondevice/firmware && pio clean && pio build -e edge-rl-node

# 6. Check builds succeeded
# Both should end with "BUILD SUCCESSFUL"

# 7. For on-device: verify Docker broker
docker ps | grep mosquitto

# 8. Restart Wokwi from scratch
# In VS Code: F1 → "Wokwi: Restart Simulator"
```

---

## ❓ Still No Logs?

If you've gone through all steps and still no output:

**Try this nuclear option:**

1. **Close VS Code completely**
2. **Clear Wokwi cache:**
   ```bash
   rm -rf ~/.wokwi ~/.wokwi-cache ~/.platformio
   ```
3. **Reopen VS Code**
4. **Rebuild firmware:**
   ```bash
   cd edge-rl-ondevice/firmware
   pio build -e edge-rl-node
   ```
5. **Start simulator fresh:**
   ```bash
   F1 → "Wokwi: Start Simulator"
   ```

**Wait full 10 seconds** after start.

---

## 🎯 Expected Output for Each Simulation

### On-Cloud Expected Output
```
Attempting WiFi connection...
Connected to WiFi! IP: 192.168.4.1
Connecting to MQTT broker...
MQTT connected to broker.hivemq.com
Subscribing to topics...
Subscribed to edge/zone-a/request
Subscribed to edge/zone-a/policy
Ready! Waiting for requests...
[Req] Received: sensor-01/temperature
[Inference] Processing...
[Result] Latency: 45.2ms
```

### On-Device Expected Output
```
Attempting WiFi connection...
Connected to WiFi! IP: 192.168.4.1
Connecting to MQTT broker...
MQTT connected to localhost:1883
Q-table initialized (256 states × 2 actions)
Ready! Waiting for requests...
[Req] Request: cnc-01/vibration
[RL] Computing Q-values...
[Learn] TD_error = 0.045, eps = 0.890
[Cache] HIT!
```

---

## 📱 Tab Organization

**Wokwi Window should look like this:**

```
┌──────────────────────────────────────────────────┐
│ 🔌 Wokwi Simulator - edge-rl-ondevice             │
├──────────────────────────────────────────────────┤
│ [Board 🖱] [Serial 📡] [GDB 🐛]    [⚙️ Sim]     │  Board View Tabs
├──────────────────────────────────────────────────┤
│                                                  │
│    [ESP32 Board Visualization Here]              │
│                                                  │
│    💡 LED                                        │
│    🔘 Button                                     │
│                                                  │
├──────────────────────────────────────────────────┤
│ [Wokwi Terminal 📌] [Terminal]  ← Click here    │
├──────────────────────────────────────────────────┤
│                                                  │
│ [UART] Attempting WiFi connection...            │ ← YOUR LOGS
│ [UART] Connected to WiFi!                       │
│ [UART] MQTT connected to localhost:1883         │
│        ...                                       │
│                                                  │
└──────────────────────────────────────────────────┘
```

**Key:** Click **"Wokwi Terminal 📌"** tab to see serial output.

---

## 🆘 If Still Stuck

1. Check [WOKWI_SETUP.md](../WOKWI_SETUP.md) → Troubleshooting
2. Check [README.md](../README.md) → Quick Start
3. Try the "Nuclear Option" above
4. Post error messages in project issues

---

**Last Updated:** April 15, 2026  
**Common Fix:** 95% of time = clicked wrong tab or need to rebuild  
**Status:** ✅ Should Fix Your Issue
