A fully virtualized multi-agent reinforcement learning (MARL) system that teaches
ESP32 edge nodes to make smart caching decisions in real time.

**Demo focus:** contrast a full **TD3 + LTC (ncps AutoNCP) policy on CPU** vs a **quantized int8 8-weight edge policy**
running on **simulated ESP32 nodes (Wokwi)**, using the same MQTT message flow and training loop.

Built with: Python · PyTorch · ncps · PlatformIO · Wokwi · Docker · Eclipse Mosquitto

## Key docs

- `IMPLEMENTED_ARCHITECTURE.md`: end-to-end explanation of what’s implemented
- `demo/README.md`: exact commands for the demo workflow (dashboard + compare mode)

## Quickstart (virtual factory use case)

### Control plane (Zone 2)

```bash
docker compose up --build
```

This starts:
- Mosquitto MQTT broker (`:1883`)
- TD3 trainer (twin critics, target smoothing, delayed policy updates, soft targets) + shared replay buffer
- Bursty traffic generator (500KB–2MB bursts every 30s)

### Live dashboard (teacher-visible)

```bash
python demo/dashboard.py
```

### Simulated edge nodes (Zone 3)

```bash
cd firmware
pio run -e zone-a
pio run -e zone-b
```

Run two Wokwi CLI instances (one per node). The firmware:
- subscribes to `edge/<node_id>/request`
- publishes `edge/<node_id>/telemetry` with hit/miss/latency + int8 score + decision metadata
- listens for policy updates on `edge/<node_id>/policy`

### CPU vs Edge policy comparison (key differentiator)

```bash
python demo/compare_mode.py
```
