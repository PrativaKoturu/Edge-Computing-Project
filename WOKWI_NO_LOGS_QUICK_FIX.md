# 🚨 WOKWI NO LOGS - QUICK FIX GUIDE

## ⚡ 30-Second Fix

```
1. In Wokwi window → Click "Wokwi Terminal" tab (NOT "Terminal" tab)
   ↓
2. See logs? ✅ DONE!
   See nothing? ↓
3. Press F1 → Type "Wokwi: Stop Simulator" → Wait 2 sec
   ↓
4. Press F1 → Type "Wokwi: Start Simulator" → Wait 10 sec
   ↓
5. Click "Wokwi Terminal" tab again
   ↓
6. See logs now? ✅ DONE!
```

---

## 🔍 If Still Nothing - Try These in Order

### Fix #1: Check Simulator is Running
```
Look at bottom-right of VS Code
Should show green Wokwi icon "Wokwi Simulator Running"

If not:
  F1 → "Wokwi: Start Simulator"
  Wait 15 seconds
```

### Fix #2: Rebuild Firmware
```bash
# For on-device:
cd edge-rl-ondevice/firmware
pio clean -e edge-rl-node
pio build -e edge-rl-node

# For on-cloud:
cd edge-rl-oncloud/firmware
pio clean -e zone-a
pio build -e zone-a

# Should end with: "BUILD SUCCESSFUL"
```

### Fix #3: Check Baud Rate
```
Open: edge-rl-ondevice/firmware/wokwi.toml
     (or edge-rl-oncloud/firmware/wokwi.toml)

Should have:
  [[wokwi.uart]]
  index = 0
  baud = 115200    ← This should be 115200
```

### Fix #4: Check Serial Config
```
Open: edge-rl-ondevice/firmware/diagram.json
     (or edge-rl-oncloud/firmware/diagram.json)

Should have at bottom:
  "serial": [
    {
      "type": "serial",
      "target": "esp32"
    }
  ]

If missing, add it!
```

### Fix #5: Nuclear Reset
```bash
# Clear all Wokwi cache
rm -rf ~/.wokwi ~/.wokwi-cache

# Restart VS Code completely (close and reopen)

# Rebuild:
cd edge-rl-ondevice/firmware
pio clean && pio build -e edge-rl-node

# Start fresh:
F1 → "Wokwi: Start Simulator"
Wait 10 seconds
```

---

## 📍 WHERE TO FIND LOGS

```
VS Code Window
    ↓
┌─────────────────────────────────────────┐
│ Main Editor                             │
├─────────────────────────────────────────┤
│ [Wokwi Simulator Pane]                  │
│ ┌───────────────────────────────────┐   │
│ │ Board  Serial  GDB  ⚙️            │   │
│ ├───────────────────────────────────┤   │
│ │                                   │   │
│ │  (ESP32 Drawing Here)             │   │
│ │                                   │   │
│ ├───────────────────────────────────┤   │
│ │[Wokwi Terminal 📌] [Terminal]    │← CLICK HERE!
│ │                                   │
│ │ Your logs appear here!            │
│ │ (Now showing serial output)       │
│ │                                   │
│ └───────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

**Most common mistake: Clicking wrong tab!**

---

## ✅ CORRECT SETUP

### For On-Cloud (edge-rl-oncloud)

**wokwi.toml:**
```toml
[[wokwi.uart]]
index = 0
baud = 115200          ✅
```

**diagram.json:**
```json
"serial": [{
  "type": "serial",
  "target": "esp32"
}]                     ✅
```

**platformio.ini:**
```ini
[env:zone-a]
build_flags =
  -DNODE_ID='"zone-a"'        ✅
```

### For On-Device (edge-rl-ondevice)

**wokwi.toml:**
```toml
[[wokwi.uart]]
index = 0
baud = 115200          ✅
```

**diagram.json:**
```json
"serial": [{
  "type": "serial",
  "target": "esp32"
}]                     ✅
```

**platformio.ini:**
```ini
[env:edge-rl-node]
build_flags =
  -DNODE_ID='"edge-rl-node"'  ✅
```

---

## 🧪 VERIFY SERIAL CODE

```bash
# Should find Serial.begin in both files:
grep "Serial.begin" edge-rl-oncloud/firmware/src/main.cpp
grep "Serial.begin" edge-rl-ondevice/firmware/src/main.cpp

# Output should be:
# edge-rl-oncloud/firmware/src/main.cpp:237:  Serial.begin(115200);
# edge-rl-ondevice/firmware/src/main.cpp:370:    Serial.begin(115200);
```

If not found, add to `setup()` function:
```cpp
void setup() {
  Serial.begin(115200);
  delay(1000);
  // ... rest
}
```

---

## 🎯 EXPECTED FIRST LOGS

### On-Cloud Should Show:
```
Attempting WiFi connection...
Connected to WiFi! IP: 192.168.4.1
Connecting to MQTT broker...
MQTT connected to broker.hivemq.com
```

### On-Device Should Show:
```
Attempting WiFi connection...
Connected to WiFi! IP: 192.168.4.1
Connecting to MQTT broker...
MQTT connected to localhost:1883
```

---

## 📞 STILL NOT WORKING?

1. **Read full guide:** [WOKWI_SERIAL_TROUBLESHOOTING.md](WOKWI_SERIAL_TROUBLESHOOTING.md)
2. **Check project:** [WOKWI_SETUP.md](WOKWI_SETUP.md) → Troubleshooting
3. **Last resort:** Follow "Nuclear Reset" above

---

**Pro Tip:** Logs usually appear **3-5 seconds after clicking "Wokwi Terminal" tab**

**99% of the time:** You clicked the wrong tab! 😄
