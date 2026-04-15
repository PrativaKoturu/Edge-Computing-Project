# 📋 MQTT Fix - Quick Reference

## Problem
- Wokwi ESP32 tried: `localhost:1883`
- Docker broker is on host machine
- Networks don't talk → **Connection timeout** ❌

## Solution
- Use: `host.wokwi.internal:1883` (special Wokwi DNS)
- Automatically tunnels to your host machine ✅

## What Changed
| File | Before | After |
|------|--------|-------|
| `wokwi.toml` | `host = "localhost"` | `host = "host.wokwi.internal"` |
| `platformio.ini` | `-DMQTT_HOST='"localhost"'` | `-DMQTT_HOST='"host.wokwi.internal"'` |

## What to Do Now

**In VS Code:**
1. Press `F1` → Type `"Wokwi: Stop Simulator"` → Wait 2s
2. Press `F1` → Type `"Wokwi: Start Simulator"` → Wait 15s
3. Click **"Wokwi Terminal"** tab
4. Look for: `[mqtt] Connected` ✅

**Expected logs:**
```
[wifi] Connected  ip=192.168.4.12
[mqtt] Connecting host.wokwi.internal:1883  id=edge-rl-XXXXX
[mqtt] Connected. Subscribed: edge/edge-rl-node/request
[REQ] Request received: stream=cnc-01/vibration
[LEARN] Q updated
[CACHE] HIT!
```

## Verification
```bash
# Docker should show connection
docker logs mosquitto-ondevice | tail -2
# Should show: Received CONNECT from edge-rl-node
```

---

✅ **All changes applied automatically!**  
Just restart Wokwi and watch the logs.

For detailed info → [MQTT_WOKWI_FIX.md](MQTT_WOKWI_FIX.md)
