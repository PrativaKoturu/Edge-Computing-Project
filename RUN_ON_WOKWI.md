# Running on Wokwi: Complete Guide

Two ways to run the firmware on actual Wokwi ESP32 simulators.

---

## Method 1: Wokwi Web IDE (Easiest - 5 minutes)

### Step 1: Go to Wokwi.com

Open: https://wokwi.com/

### Step 2: Create New Arduino Project

- Click "Create New Project" (or "+" button)
- Select "Arduino" → "Arduino Uno" (or "ESP32")
- Click "Create"

### Step 3: Replace Template Code

Copy your firmware from:
```
firmware/src/main.cpp
```

Paste it into the Wokwi editor (replace all template code).

### Step 4: Configure MQTT Host

In the code, find:
```cpp
#ifndef MQTT_HOST
#define MQTT_HOST "host.wokwi.internal"
#endif
```

This is already set correctly for Wokwi. ✓

### Step 5: Start Simulation

Click the **Play button** (▶️) to run.

### Step 6: Watch Serial Output

You should see:
```
[Boot] zone-a
[WiFi] Connecting SSID=Wokwi-GUEST
[WiFi] Connected
[MQTT] Connecting mqtt:1883...
[MQTT] Connected. Subscribed: edge/zone-a/request, edge/zone-a/policy
```

### Step 7: Create Second Tab for Zone B

Repeat steps 1-6 but for zone-b:
- Change code to use `NODE_ID "zone-b"`
- Open in separate browser tab

---

## Method 2: VS Code Extension (Better - 3 minutes)

### Step 1: Install VS Code Extension

In VS Code:
1. Go to Extensions (Cmd+Shift+X)
2. Search for "Wokwi"
3. Click "Install" on "Wokwi - Simulator for Arduino & MicroController"

### Step 2: Open Your Project

```bash
cd /Users/prativa/Documents/GitHub/Edge-Computing-Project
code .
```

### Step 3: Create wokwi.toml

In `firmware/` folder, create file `wokwi.toml`:

```toml
[wokwi]
version = 1
firmware = "src/main.cpp"

[[chip]]
name = "esp32"
```

### Step 4: Start Simulator

In VS Code, press **Cmd+Shift+P** and type:
```
Wokwi: Start Simulator
```

Or click the Wokwi icon (circuit board) in bottom status bar.

### Step 5: View Serial Monitor

The simulator opens a panel showing:
```
[Boot] zone-a
[WiFi] Connecting...
[MQTT] Connected
```

### Step 6: Run Zone B in Parallel

Open a second VS Code window:
```bash
code . --new-window
```

Same steps, but VS Code runs zone-b in parallel.

---

## Method 3: Wokwi CLI (If npm Works)

If npm can install from GitHub:

```bash
npm install -g https://github.com/wokwi/wokwi-cli
```

Then:
```bash
cd firmware
wokwi-cli --build-type pio --project . zone-a
```

(Try Methods 1-2 first, these are easier)

---

## Full Demo: 4 Terminals + 2 Browser Tabs

Here's the **complete setup** to show everything:

### Terminal 1: Control Plane

```bash
docker compose up --build
```

Wait for:
```
trainer    | INFO trainer: Trainer loop started. Nodes=zone-a,zone-b
traffic    | INFO traffic: Traffic generator started.
```

✅ Trainer is running on your machine, waiting for telemetry.

---

### Browser Tab 1: Zone A on Wokwi

Go to: https://wokwi.com/

1. Create new Arduino project
2. Paste `firmware/src/main.cpp`
3. Click ▶️ to run

Watch for:
```
[Boot] zone-a
[MQTT] Connected. Subscribed: edge/zone-a/request, edge/zone-a/policy
[req] stream=cnc-01/vibration payload=1200KB anomaly=0 hit=0 latency=1523ms
[score] i32=12345 decision=1
```

✅ Zone A receiving requests from trainer traffic generator!

---

### Browser Tab 2: Zone B on Wokwi

Same as Tab 1, but:
- Create second Wokwi project
- Same code, Wokwi auto-detects NODE_ID "zone-b"

Or manually change in code:
```cpp
#define NODE_ID "zone-b"
```

Watch for same messages as Zone A.

✅ Zone B running independently!

---

### Terminal 2: Watch Telemetry

```bash
docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry" | head -20
```

You'll see JSON from both zones:
```json
{"node_id":"zone-a","cache_hit":false,"latency_ms":1523,...}
{"node_id":"zone-b","cache_hit":true,"latency_ms":45,...}
```

✅ Both zones sending telemetry to trainer!

---

### Terminal 3: Monitor Trainer

```bash
docker compose logs -f trainer | grep -E "Replay|updates|loss"
```

Watch for:
```
trainer    | INFO trainer: Replay size=50 latest node=zone-a hit=False
trainer    | INFO trainer: Replay size=100 latest node=zone-b hit=True
trainer    | INFO trainer: updates=50 critic_loss(avg10)=0.2345
trainer    | INFO trainer: updates=100 critic_loss(avg10)=0.1234
```

✅ Trainer learning from both zones!

---

### Terminal 4: Live Dashboard

```bash
python3 demo/wokwi_comparison_dashboard.py
```

Shows all 3 systems side-by-side:
```
┌─ ZONE-A (Wokwi ESP32) ─┐
Requests: 45
Cache Hits: 4 (8.9%)

┌─ ZONE-B (Wokwi ESP32) ─┐
Requests: 42
Cache Hits: 5 (11.9%)

┌─ CONTROL PLANE (Your CPU) ─┐
Critic Updates: 150
Critic Loss: 0.0987 ↓
```

✅ Real-time comparison dashboard!

---

## What You're Seeing (Timeline)

```
t=0s:    Terminal 1: Trainer starts
         
t=5s:    Browser Tab 1: Zone A boots, connects to MQTT
         Browser Tab 2: Zone B boots, connects to MQTT
         Serial output: [MQTT] Connected
         
t=10s:   Terminal 1: Traffic generator sends first burst
         Browser Tab 1-2: [req] messages appear
         Terminal 2: First telemetry JSON appears
         Terminal 4: Dashboard shows "Requests: 1, 2, 3..."
         
t=30s:   Terminal 1: Replay size=30, 40, 50...
         Terminal 3: updates=10, 20, 30...
         Terminal 4: Critic Loss starts decreasing (0.5 → 0.3)
         
t=120s:  Terminal 1: "policy publishes to zones"
         Browser Tab 1-2: [policy] updated messages appear
         Terminal 4: Policy Publishes counter increases (0 → 1)
         
t=180s:  Terminal 4: Hit rates improving (2% → 8% → 12%)
         Both zones showing similar hit rates
         PROOF: Zones are learning together!
```

---

## Proof It's Working

Watch for these signs:

| Sign | Location | What It Means |
|------|----------|---------------|
| `[MQTT] Connected` | Wokwi serial output | Zone connected to trainer |
| `Replay size=50+` | Terminal 1 | Trainer receiving telemetry |
| `updates=50+` | Terminal 1 | Training happening |
| `critic_loss` decreasing | Terminal 3 | Model learning |
| `[policy] updated` | Wokwi serial output | Trainer sent new policy |
| `Hit Rate: 0% → 12%` | Terminal 4 dashboard | Policy working! |

---

## Troubleshooting Wokwi

### "MQTT Connection Failed"

**Problem:** Wokwi can't connect to trainer.

**Check:**
1. Is docker compose running? (Terminal 1)
2. Does Wokwi show WiFi connected? (Check serial output)
3. Are you using `host.wokwi.internal`? (Should be automatic)

**Fix:**
- Restart Wokwi (refresh browser or restart VS Code)
- Check: `docker compose logs mqtt`

### "No Requests Appearing"

**Problem:** Zone not receiving traffic.

**Check:**
```bash
docker compose exec mqtt mosquitto_sub -t "edge/+/request"
```

Should show JSON requests flowing in.

**Fix:**
- Is trainer running? (Terminal 1 should show "Traffic generator started")
- Is zone subscribed to the right topic? (Check serial: should say "Subscribed: edge/zone-a/request")

### "Trainer Not Receiving Telemetry"

**Problem:** Terminal 1 still shows "Replay size=0"

**Check:**
```bash
docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry"
```

Should show JSON from zones.

**Fix:**
- Is zone sending telemetry? (Check Wokwi serial for `[score]` messages)
- Is zone connected to MQTT? (Should show `[MQTT] Connected`)

---

## Recommended Setup

**Best experience: Use Method 1 (Web IDE) for simplicity**

1. **Terminal 1:** `docker compose up --build`
2. **Browser Tab 1:** Wokwi web IDE with zone-a firmware (https://wokwi.com/)
3. **Browser Tab 2:** Wokwi web IDE with zone-b firmware (https://wokwi.com/)
4. **Terminal 2:** `docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry"`
5. **Terminal 3:** `docker compose logs -f trainer | grep -E "Replay|updates"`
6. **Terminal 4:** `python3 demo/wokwi_comparison_dashboard.py`

This gives you:
- ✅ Real Wokwi simulators running firmware
- ✅ Real MQTT communication with trainer
- ✅ Real learning happening
- ✅ Pretty dashboard showing everything

---

## What to Show Your Teacher

### "Here are two real ESP32 simulators"

Point to: Browser Tab 1 & 2 running Wokwi

Serial output shows:
```
[MQTT] Connected
[req] stream=cnc-01/vibration ...
[score] i32=12345 decision=1
```

"Both zones running the same int8 policy, independent caches."

---

### "Here's my trainer learning on CPU"

Point to: Terminal 1 and 3

```
Replay size=100  ← Both zones sending telemetry
updates=50 critic_loss=0.234  ← Training happening
[policy] published  ← Trainer sent optimized policy
```

"Trainer learns from both zones, publishes better policies."

---

### "Here's the real-time comparison"

Point to: Terminal 4 Dashboard

```
Zone A Hit Rate: 9% (independent cache)
Zone B Hit Rate: 12% (independent cache)
Critic Loss: 0.234 ↓ (training happening)
```

"Both zones maintain independent caches but learn together."

---

## Final Checklist

- [ ] Docker compose running (Terminal 1)
- [ ] Zone A firmware loaded in Wokwi (Browser Tab 1)
- [ ] Zone B firmware loaded in Wokwi (Browser Tab 2)
- [ ] Both zones showing "[MQTT] Connected"
- [ ] Terminal 1 showing "Replay size > 0"
- [ ] Requests appearing in Wokwi serial
- [ ] Dashboard updating with metrics
- [ ] Hit rates improving over time

✅ **You're ready to present!**

---

## Quick Reference Commands

```bash
# Terminal 1: Trainer
docker compose up --build

# Terminal 2: Watch telemetry
docker compose exec mqtt mosquitto_sub -t "edge/+/telemetry" | head -20

# Terminal 3: Watch trainer logs
docker compose logs -f trainer | grep -E "Replay|updates|loss"

# Terminal 4: Dashboard
python3 demo/wokwi_comparison_dashboard.py

# Browser: Wokwi projects
https://wokwi.com/
# New Project → Arduino ESP32 → Paste firmware → Click Play
```

---

**Ready? Open Wokwi and paste the firmware!** 🚀
