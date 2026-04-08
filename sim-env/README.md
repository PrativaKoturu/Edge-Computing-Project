## Running the full virtual factory-loop

### 1) Start the control plane (MQTT + trainer + traffic)

From repo root:

```bash
docker compose up --build
```

You should see:
- Mosquitto broker logs
- `traffic` emitting a burst every 30 seconds
- `trainer` reporting replay size / critic updates

### 2) Start two Wokwi ESP32 nodes

In another terminal:

```bash
cd firmware
pio run -e zone-a
pio run -e zone-b
```

Then run **two** Wokwi simulations (one per node) using the Wokwi CLI, each pointing at the correct build output.

Notes:
- The firmware connects to WiFi SSID `Wokwi-GUEST`
- The firmware connects to MQTT host `host.wokwi.internal:1883`

### Topics (for debugging)

- `edge/<node_id>/request` traffic generator → edge node
- `edge/<node_id>/telemetry` edge node → trainer
- `edge/<node_id>/policy` trainer → edge node
