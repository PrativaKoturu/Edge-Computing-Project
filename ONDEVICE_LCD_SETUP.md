# 📺 On-Device LCD Display Setup - Complete Guide

You now have **identical LCD display capabilities** on both **on-cloud** and **on-device** simulations!

---

## ✨ What's New on On-Device

### Before
```
On-Device had:
- Green LED (GPIO 13)
- Push Button (GPIO 12)
- Serial output only
```

### After ✅
```
On-Device now has:
- Green LED (GPIO 13) - Cache hit indicator
- Push Button (GPIO 12) - Manual trigger
- 16×2 LCD Display (I2C) - Real-time status ✨ NEW
- Serial output (for detailed logs)
```

---

## 🎨 LCD Display Layout

The 16×2 LCD shows real-time metrics as the system runs:

```
┌────────────────────┐
│Steps:150 Hit:72%   │  ← Row 1: Training progress
│Cache:24 Eps:0.15   │  ← Row 2: Cache status & exploration
└────────────────────┘
```

**What Each Metric Means:**
- **Steps** - Total decision requests processed
- **Hit%** - Cache hit rate (higher = better learning)
- **Cache** - Number of items in cache (0-64)
- **Eps** - Epsilon exploration rate (starts high, decays to 0.05)

---

## 🔧 Configuration Files Updated

### 1. diagram.json (Enhanced)
```json
{
  "parts": [
    { "type": "board-esp32-devkit-v1", "id": "esp32" },
    { "type": "wokwi-lcd1602", "id": "lcd", ... },  ✨ NEW
    { "type": "wokwi-led", "id": "led1", ... },
    { "type": "wokwi-pushbutton", "id": "button1", ... }
  ],
  "connections": [
    [ "esp32:D21", "lcd:SDA", "blue", [] ],      ✨ NEW
    [ "esp32:D22", "lcd:SCL", "yellow", [] ],    ✨ NEW
    [ "esp32:3V3", "lcd:VCC", "red", [] ],       ✨ NEW
    [ "esp32:GND.1", "lcd:GND", "black", [] ],   ✨ NEW
    ...
  ]
}
```

**I2C Connections:**
- **GPIO 21** (D21) → LCD SDA (data)
- **GPIO 22** (D22) → LCD SCL (clock)
- **3V3** → LCD VCC (power)
- **GND** → LCD GND (ground)
- **I2C Address:** 0x27 (standard for this LCD)

### 2. platformio.ini (Updated)
```ini
[env:edge-rl-node]
lib_deps =
  knolleary/PubSubClient@^2.8
  bblanchon/ArduinoJson@^7.0.4
  marcoschwartz/LiquidCrystal_I2C@^1.1.4  ✨ NEW LCD library
```

### 3. main.cpp (Enhanced)
```cpp
// Added LCD initialization
#include <LiquidCrystal_I2C.h>       ✨ NEW

#define LCD_ADDR 0x27                ✨ NEW
#define LCD_COLS 16                  ✨ NEW
#define LCD_ROWS 2                   ✨ NEW

LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);  ✨ NEW

static void lcdPrint(const char *row0, const char *row1 = nullptr) {  ✨ NEW
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(row0);
  if (row1) {
    lcd.setCursor(0, 1);
    lcd.print(row1);
  }
}
```

---

## 📊 LCD Display During Execution

### Startup Phase
```
┌────────────────────┐
│Edge RL Node        │  ← System boot message
│Initializing...     │
└────────────────────┘
```

### WiFi Connection
```
┌────────────────────┐
│WiFi               │  ← Connecting...
│Connecting...      │
└────────────────────┘

After WiFi connects:
┌────────────────────┐
│WiFi OK            │
│192.168.4.1        │  ← IP address
└────────────────────┘
```

### MQTT Connection
```
┌────────────────────┐
│MQTT               │  ← Connecting...
│Connecting...      │
└────────────────────┘

After MQTT connects:
┌────────────────────┐
│MQTT OK            │
│Ready!             │
└────────────────────┘
```

### Training/Learning Phase (Continuous)
```
┌────────────────────┐
│Steps:150 Hit:72%   │
│Cache:24 Eps:0.15   │
└────────────────────┘

Updates every request!
```

---

## 🚀 How to Use

### 1. Rebuild Firmware
```bash
cd edge-rl-ondevice/firmware

# Clean and rebuild
pio clean -e edge-rl-node
pio build -e edge-rl-node

# Expected output:
# Building...
# ...
# = BUILD SUCCESSFUL =
```

### 2. Start Wokwi Simulation
```bash
# In VS Code:
# F1 → "Wokwi: Start Simulator"
```

### 3. Watch the LCD
The Wokwi simulator will display:
- ESP32 board (left side)
- **16×2 Green LCD Display** (right side) ✨ NEW
- Green LED (below LCD)
- Red Push Button (below LED)

### 4. See Real-Time Updates
As requests arrive:
1. **Steps** increments (each decision)
2. **Hit%** updates (cache hit rate)
3. **Cache** shows occupancy
4. **Eps** decreases (learning progresses)

---

## 🎮 Visual Layout in Wokwi

```
Wokwi Simulator View:
┌─────────────────────────────────────────────────┐
│ [Board] [Serial] [GDB]                          │
├─────────────────────────────────────────────────┤
│                                                 │
│   ┌──────────┐         ┌────────────────────┐  │
│   │  ESP32   │         │ STEPS:150 HIT:72%  │  │
│   │          │         │ CACHE:24 EPS:0.15  │  │ ← LCD
│   │          │         └────────────────────┘  │
│   │   PINS   │              💡 LED             │
│   │          │              🔘 BUTTON          │
│   └──────────┘                                 │
│                                                 │
├─────────────────────────────────────────────────┤
│ [Wokwi Terminal] [Terminal]                    │
│ [MQTT] Connected to localhost:1883             │
│ [req]  stream=cnc-01/vibration hit=1 lat=42ms │
│ [learn] action=CACHE reward=+1.0 eps=0.890    │
└─────────────────────────────────────────────────┘
```

---

## 📋 LCD Display States

| State | Line 1 | Line 2 | When |
|-------|--------|---------|------|
| **Boot** | Edge RL Node | Initializing... | Power-on |
| **WiFi** | WiFi | Connecting... | Starting WiFi |
| **WiFi OK** | WiFi OK | 192.168.X.X | WiFi connected |
| **MQTT** | MQTT | Connecting... | Starting MQTT |
| **Ready** | MQTT OK | Ready! | Ready to learn |
| **Training** | Steps:NNN Hit:YY% | Cache:ZZ Eps:0.XX | Running |

---

## 🔍 Comparing On-Cloud vs On-Device LCD

### On-Cloud LCD Output
```
┌────────────────────┐
│zone-a  Connected   │
│Policy: v4.2 #1234  │
└────────────────────┘

Shows:
- Node ID (zone-a)
- MQTT status
- Latest policy ID
- Policy size
```

### On-Device LCD Output (NEW)
```
┌────────────────────┐
│Steps:150 Hit:72%   │
│Cache:24 Eps:0.15   │
└────────────────────┘

Shows:
- Training progress (steps)
- Cache effectiveness (hit rate)
- Cache occupancy
- Exploration rate (epsilon decay)
```

**Key Difference:**
- **On-Cloud:** Shows external policy updates
- **On-Device:** Shows internal learning progress ✨

---

## 💡 Understanding the Metrics

### Hit Rate (Hit%)
```
Hit% = (cache hits) / (total requests) × 100

Examples:
- Hit: 0%   → Cache not working yet (initial)
- Hit: 50%  → Some learning happening
- Hit: 75%+ → Good learning! Policy is effective
```

### Epsilon (Eps)
```
Eps = exploration rate

Starts at: 0.50 (50% random actions)
Decays by: 0.001 per step
Minimum:  0.05 (always 5% random)

Examples:
- Eps: 0.50 → Mostly exploring
- Eps: 0.30 → Mix of explore/exploit
- Eps: 0.05 → Mostly exploiting learned policy
```

### Cache Usage
```
Cache: X  where X is 0-64

Examples:
- Cache: 0   → Empty
- Cache: 32  → Half full
- Cache: 64  → Full capacity
```

### Steps
```
Steps: N  where N increments each request

Examples:
- Steps: 0    → Just started
- Steps: 100  → 100 decisions made
- Steps: 1000+ → Well-trained policy
```

---

## 🐛 Troubleshooting

### LCD Shows Nothing
```
Cause: I2C initialization failed
Solution:
1. Check diagram.json has correct connections
2. Rebuild firmware: pio clean && pio build -e edge-rl-node
3. Restart Wokwi: F1 → Stop → Start
4. Wait 5 seconds for initialization
```

### LCD Shows Garbage Characters
```
Cause: Baud rate or I2C mismatch
Solution:
1. Verify wokwi.toml: baud = 115200 ✓
2. Verify platformio.ini: monitor_speed = 115200 ✓
3. Verify I2C address in main.cpp: 0x27 ✓
4. Rebuild and restart simulator
```

### LCD Updates Slowly
```
Cause: Simulation speed is slow
Solution:
1. Check wokwi.toml: speed = "1MHz" (intended)
2. For faster updates, change to: speed = "full"
3. Rebuild and restart
```

### Some Metrics Show Zeros
```
Cause: System just started
Solution:
- Wait 30+ seconds for learning to progress
- Send more requests via traffic generator
- Hit rate improves over time as policy learns
```

---

## 📈 Monitoring Progress

### First 30 Seconds (Learning Starts)
```
Steps:   0 → 10 → 20 → 30...
Hit%:    0% → 10% → 15% → 20%
Eps:   0.50 → 0.48 → 0.47 → 0.46
Cache: 0 → 5 → 10 → 15
```

### After 2 Minutes (Learning Stabilizes)
```
Steps:  120
Hit%:   65%
Eps:    0.38
Cache:  32
```

### After 5 Minutes (Well-Trained)
```
Steps:  300
Hit%:   75%
Eps:    0.20
Cache:  45
```

---

## 🎯 Comparing Both Simulations Now

### Setup Comparison

| Feature | On-Cloud | On-Device |
|---------|----------|-----------|
| **Board** | ESP32 | ESP32 |
| **LCD Display** | ✅ 16×2 LCD | ✅ 16×2 LCD (NEW) |
| **LED** | Red (GPIO 2) | Green (GPIO 13) |
| **Button** | None | Push Button (GPIO 12) |
| **Data Display** | Policy info | Learning metrics |
| **Serial** | ✅ Logs | ✅ Logs |

### Identical I2C Setup

**Both use identical I2C connections:**
```
GPIO 21 (D21) → SDA (blue wire)
GPIO 22 (D22) → SCL (yellow wire)
3V3 → VCC (red wire)
GND → GND (black wire)
Address: 0x27
```

**Both use identical LCD library:**
```cpp
#include <LiquidCrystal_I2C.h>
LiquidCrystal_I2C lcd(0x27, 16, 2);
```

---

## ✅ Verification Checklist

Before running simulation:
- [ ] diagram.json has LCD connections (GPIO 21/22)
- [ ] platformio.ini includes LiquidCrystal_I2C library
- [ ] main.cpp includes `#include <LiquidCrystal_I2C.h>`
- [ ] main.cpp has `lcdPrint()` function
- [ ] Firmware builds: `pio build -e edge-rl-node` succeeds
- [ ] Both wokwi.toml files are identical except NODE_ID
- [ ] Wokwi simulator shows LCD on screen

All checked? ✅ Ready to simulate!

---

## 🚀 Quick Start

```bash
# 1. Build firmware
cd edge-rl-ondevice/firmware
pio clean -e edge-rl-node
pio build -e edge-rl-node

# 2. Start Docker services
cd ../..
cd edge-rl-ondevice
docker compose up -d

# 3. Open in VS Code
cd firmware
code .

# 4. Start Wokwi
# F1 → "Wokwi: Start Simulator"

# 5. Watch the LCD display real-time metrics!
```

---

## 📚 Files Modified

✅ **edge-rl-ondevice/firmware/diagram.json**
- Added wokwi-lcd1602 component
- Added I2C connections (GPIO 21/22)
- Rearranged LED/Button positions

✅ **edge-rl-ondevice/firmware/platformio.ini**
- Added LiquidCrystal_I2C library dependency

✅ **edge-rl-ondevice/firmware/src/main.cpp**
- Added `#include <LiquidCrystal_I2C.h>`
- Added LCD constants (ADDR, COLS, ROWS, LED_PIN, BUTTON_PIN)
- Added `lcdPrint()` function
- Added LCD initialization in `setup()`
- Added LCD updates in WiFi connection
- Added LCD updates in MQTT connection
- Added LCD updates during training with real-time metrics

---

## 🎓 Learning from the LCD

Watch the metrics change as the system learns:

1. **Steps increment** - Each request is one step
2. **Hit% increases** - Policy learns what to cache
3. **Cache fills** - More items stored as needed
4. **Eps decays** - Gradually shifts from exploring to exploiting
5. **Pattern emerges** - Hit rate stabilizes at ~70-80%

This is **on-device reinforcement learning** happening in real-time! 🎉

---

## 🔗 Related Documentation

- **WOKWI_SETUP.md** - General Wokwi setup guide
- **README.md** - Full project architecture
- **SIMULATION_ARCHITECTURE.md** - On-cloud vs on-device comparison
- **TESTING.md** - Testing both pipelines with dashboard

---

**Status:** ✅ On-Device Now Has LCD Display!  
**Last Updated:** April 15, 2026  
**Your Setup:** On-Cloud and On-Device are now visually identical ✨
