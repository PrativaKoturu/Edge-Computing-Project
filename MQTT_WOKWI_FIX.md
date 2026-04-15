# 🔧 MQTT Connection Troubleshooting - Wokwi Simulator

## Problem Diagnosis

Your setup shows:
- ✅ Docker Mosquitto broker running on `localhost:1883`
- ✅ Traffic generator publishing requests (`edge/edge-rl-node/request`)
- ❌ Wokwi ESP32 simulator cannot connect to MQTT

## Root Cause

**Wokwi's virtual network is isolated from your host's Docker network.**

When Wokwi simulator tries to connect to `localhost:1883`:
- It's looking for `localhost` **inside the simulated network**
- Not your host machine's `localhost`
- Docker broker is not accessible from inside Wokwi

## Solutions

---

## ✅ Solution 1: Use `host.wokwi.internal` (RECOMMENDED)

Wokwi provides a special hostname that tunnels through to your host machine.

### Step 1: Update `wokwi.toml`

**File:** `edge-rl-ondevice/firmware/wokwi.toml`

Change the network host from:
```toml
[[wokwi.network]]
host = "localhost"
port = 1883
```

To:
```toml
[[wokwi.network]]
host = "host.wokwi.internal"
port = 1883
```

### Step 2: Update `platformio.ini`

**File:** `edge-rl-ondevice/firmware/platformio.ini`

Change:
```ini
-DMQTT_HOST='"localhost"'
```

To:
```ini
-DMQTT_HOST='"host.wokwi.internal"'
```

### Step 3: Rebuild and Test

```bash
cd edge-rl-ondevice/firmware
pio build -e edge-rl-node
# Then restart Wokwi: F1 → "Wokwi: Stop Simulator"
# Then: F1 → "Wokwi: Start Simulator"
```

### Why This Works

`host.wokwi.internal` is a **special DNS name** that:
- Wokwi recognizes in its simulated network
- Automatically routes to your **host machine's localhost**
- Allows ESP32 to reach your Docker containers
- Works for any port: 1883, 8080, 5000, etc.

---

## ✅ Solution 2: Use Public MQTT Broker (Quick Test)

If `host.wokwi.internal` doesn't work, use a public broker temporarily:

### Option A: HiveMQ Public Broker
```ini
# In platformio.ini
-DMQTT_HOST='"broker.hivemq.com"'
-DMQTT_PORT=1883
```

**Pros:** Works immediately, no network issues  
**Cons:** Shared public broker, may have latency, data visible to others

### Option B: Eclipse IoT Broker
```ini
-DMQTT_HOST='"iot.eclipse.org"'
-DMQTT_PORT=1883
```

---

## ✅ Solution 3: Local Wokwi Network (Advanced)

**For testing multiple simulated devices together:**

This requires more complex setup. Use **Solution 1** first (recommended).

---

## 🔍 Verification Steps

After applying Solution 1:

### Step 1: Check `wokwi.toml` is correct
```bash
cat edge-rl-ondevice/firmware/wokwi.toml
# Should show: host = "host.wokwi.internal"
```

### Step 2: Check `platformio.ini` is correct
```bash
cat edge-rl-ondevice/firmware/platformio.ini | grep MQTT_HOST
# Should show: -DMQTT_HOST='"host.wokwi.internal"'
```

### Step 3: Rebuild firmware
```bash
cd edge-rl-ondevice/firmware
pio build -e edge-rl-node
# Should end with: "= BUILD SUCCESSFUL ="
```

### Step 4: Start simulator fresh
```
In VS Code:
1. F1 → "Wokwi: Stop Simulator"
2. Wait 2 seconds
3. F1 → "Wokwi: Start Simulator"
4. Wait for build (10-15 seconds)
5. Click "Wokwi Terminal" tab
```

### Step 5: Check for connection logs
You should see in the serial output:
```
[wifi] Connecting to Wokwi-GUEST ...
[wifi] Connected  ip=192.168.4.X
[mqtt] Connecting host.wokwi.internal:1883  id=edge-rl-XXXXX
[mqtt] Connected. Subscribed: edge/edge-rl-node/request
[mqtt] ✓ Ready!
```

---

## 📊 Complete Configuration Comparison

| Component | Current | Needed |
|-----------|---------|--------|
| **wokwi.toml host** | `localhost` ❌ | `host.wokwi.internal` ✅ |
| **platformio.ini MQTT_HOST** | `"localhost"` ❌ | `"host.wokwi.internal"` ✅ |
| **Docker broker** | ✅ Running on 1883 | ✅ No change needed |
| **Traffic generator** | ✅ Publishing | ✅ No change needed |

---

## 🚀 Step-by-Step Fix (Copy-Paste Ready)

### 1. Update wokwi.toml
```bash
cd /Users/prativa/Documents/GitHub/Edge-Computing-Project/edge-rl-ondevice/firmware

# Backup original
cp wokwi.toml wokwi.toml.backup

# Replace localhost with host.wokwi.internal
sed -i '' 's/host = "localhost"/host = "host.wokwi.internal"/g' wokwi.toml

# Verify
cat wokwi.toml
```

### 2. Update platformio.ini
```bash
# Replace in platformio.ini
sed -i '' 's/-DMQTT_HOST=.*/-DMQTT_HOST='"'"'host.wokwi.internal'"'"'/g' platformio.ini

# Verify
cat platformio.ini | grep MQTT_HOST
```

### 3. Rebuild
```bash
cd /Users/prativa/Documents/GitHub/Edge-Computing-Project/edge-rl-ondevice/firmware
pio build -e edge-rl-node
```

### 4. Restart Wokwi in VS Code
```
Press F1 → Type "Wokwi: Stop Simulator" → Wait 2s
Press F1 → Type "Wokwi: Start Simulator" → Wait 15s
Click "Wokwi Terminal" tab → Watch for [mqtt] Connected
```

---

## ✅ Expected Output After Fix

### In Wokwi Terminal:
```
[Wokwi] ESP32 boot starting...
[wifi] Connecting to Wokwi-GUEST ...
[wifi] Connected  ip=192.168.4.12
[mqtt] Connecting host.wokwi.internal:1883  id=edge-rl-a1b2c3d4
[mqtt] Connected. Subscribed: edge/edge-rl-node/request
```

### In Docker logs:
```bash
docker logs mosquitto-ondevice | tail -5
# Should show: Received CONNECT from ESP simulator
# Should show: Sending CONNACK: 0
```

### In Serial output:
```
[REQ] Request received: stream=cnc-01/vibration
[LEARN] Q[state][action] updated
[CACHE] HIT! reward=+1.0
```

---

## 🐛 If Still Not Working

### Check 1: Verify Docker broker is actually running
```bash
docker ps | grep mosquitto
# Should show: mosquitto-ondevice with port 1883->1883
```

### Check 2: Verify Docker logs for errors
```bash
docker logs mosquitto-ondevice
# Should NOT show "Error binding to port 1883"
```

### Check 3: Check Wokwi network settings
```bash
# In VS Code, open edge-rl-ondevice/firmware/wokwi.toml
# Verify the exact contents:
cat edge-rl-ondevice/firmware/wokwi.toml
```

### Check 4: Clear Wokwi cache
```bash
# Sometimes Wokwi caches old configurations
# Stop simulator first (F1 → Wokwi: Stop)
# Then delete cache:
rm -rf ~/.wokwi-cache/
# Then restart simulator
```

### Check 5: Rebuild everything clean
```bash
cd edge-rl-ondevice/firmware
rm -rf .pio build/
pio build -e edge-rl-node
```

---

## 📋 Configuration Files to Update

| File | Change | From | To |
|------|--------|------|-----|
| `wokwi.toml` | Line ~15 | `host = "localhost"` | `host = "host.wokwi.internal"` |
| `platformio.ini` | Line ~10 | `-DMQTT_HOST='"localhost"'` | `-DMQTT_HOST='"host.wokwi.internal"'` |

---

## 🎯 Summary

The **fix is simple**: Replace `localhost` with `host.wokwi.internal` in two files.

This tells Wokwi's ESP32 simulator to tunnel through to your host machine where Docker is running, allowing it to reach the Mosquitto broker.

**After this fix:**
- ✅ ESP32 can connect to MQTT broker
- ✅ ESP32 can receive requests from traffic generator
- ✅ ESP32 can publish telemetry
- ✅ Dashboard will show data
- ✅ Tests will pass

---

## 📚 Additional Resources

- [Wokwi Network Documentation](https://docs.wokwi.com/parts/wokwi-mqtt-server)
- [Wokwi Special Hostnames](https://docs.wokwi.com/guides/mqtt)
- [PubSubClient Examples](https://github.com/knolleary/pubsubclient/tree/master/examples)

---

**Last Updated:** April 15, 2026  
**Status:** ✅ Complete Troubleshooting Guide  
**License:** MIT
