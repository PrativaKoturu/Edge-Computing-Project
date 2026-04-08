from __future__ import annotations

import logging
import os
import random
import time

from .config import load_settings
from .messages import EdgeRequest
from .mqtt_client import MqttBus, MqttConfig
from .topics import request_topic


def _now_ms() -> int:
    return int(time.time() * 1000)


def _setup_logger(level: str) -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger("traffic")


def main() -> None:
    settings = load_settings()
    log = _setup_logger(settings.log_level)

    period_s = float(os.getenv("BURST_PERIOD_S", "30"))
    min_kb = int(os.getenv("BURST_MIN_KB", "500"))
    max_kb = int(os.getenv("BURST_MAX_KB", "2000"))

    bus = MqttBus(
        MqttConfig(host=settings.mqtt_host, port=settings.mqtt_port, client_id=f"traffic-{os.getpid()}"),
        logger=log,
    )
    bus.connect()

    # Larger pool to better resemble a 50+ CNC floor:
    sensors = ["vibration", "temperature", "pressure"]
    streams = [f"cnc-{i:02d}/{s}" for i in range(1, 51) for s in sensors]

    log.info(
        "Traffic generator started. period=%.1fs payload=%d-%dKB nodes=%s",
        period_s,
        min_kb,
        max_kb,
        ",".join(settings.edge_node_ids),
    )

    while True:
        burst_ts = _now_ms()
        # Bursty pattern: 50+ machines -> many streams; we random sample a subset per burst.
        burst_size = random.randint(10, 30)
        burst_freq: dict[str, int] = {}
        for _ in range(burst_size):
            stream_id = random.choice(streams)
            burst_freq[stream_id] = burst_freq.get(stream_id, 0) + 1
            anomaly = random.random() < 0.07  # ~7% bursts have anomaly
            payload_kb = random.randint(min_kb, max_kb)
            for nid in settings.edge_node_ids:
                req = EdgeRequest(node_id=nid, ts_ms=burst_ts, stream_id=stream_id, payload_kb=payload_kb, anomaly=anomaly)
                bus.publish(request_topic(nid), req.to_json(), qos=0)
        top = sorted(burst_freq.items(), key=lambda kv: kv[1], reverse=True)[:3]
        log.info("Burst sent ts=%d streams=%d top=%s", burst_ts, burst_size, top)
        time.sleep(period_s)


if __name__ == "__main__":
    main()

