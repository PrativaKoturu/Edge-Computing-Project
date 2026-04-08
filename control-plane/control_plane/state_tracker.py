from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np

from .messages import EdgeTelemetry


@dataclass
class _NodeState:
    rolling_hits: deque[bool]
    rolling_requests: deque[str]
    rolling_evictions: deque[bool]
    last_request_time: float


class PerNodeStateTracker:
    """
    Tracks per-node rolling statistics and builds the 8-D state vector specified in the project spec.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, _NodeState] = {}

    def _ensure(self, node_id: str) -> _NodeState:
        st = self._nodes.get(node_id)
        if st is not None:
            return st
        st = _NodeState(
            rolling_hits=deque(maxlen=10),
            rolling_requests=deque(maxlen=20),
            rolling_evictions=deque(maxlen=10),
            last_request_time=time.time(),
        )
        self._nodes[node_id] = st
        return st

    def build_state(
        self,
        node_id: str,
        telemetry_msg: EdgeTelemetry,
        payload_kb: int,
        anomaly_flag: float,
        stream_id: str,
    ) -> np.ndarray:
        """
        Returns np.array shape (8,) with the exact state definition.
        This is built using the current tracker memory (rolling windows) and the provided request context.
        """
        st = self._ensure(node_id)

        cache_occupancy = float(np.clip(telemetry_msg.cache_items / 64.0, 0.0, 1.0))
        latency_norm = float(np.clip(telemetry_msg.latency_ms / 2000.0, 0.0, 1.0))
        payload_norm = float(np.clip(payload_kb / 2000.0, 0.0, 1.0))
        anomaly = float(1.0 if anomaly_flag else 0.0)

        if len(st.rolling_hits) == 0:
            hit_rate_recent = 0.0
        else:
            hit_rate_recent = float(np.mean([1.0 if x else 0.0 for x in st.rolling_hits]))

        if len(st.rolling_requests) == 0:
            stream_request_freq = 0.0
        else:
            c = sum(1 for x in st.rolling_requests if x == stream_id)
            stream_request_freq = float(np.clip(c / 20.0, 0.0, 1.0))

        now = time.time()
        time_since_last_request_s = float(np.clip((now - st.last_request_time) / 30.0, 0.0, 1.0))

        if len(st.rolling_evictions) == 0:
            cache_pressure = 0.0
        else:
            cache_pressure = float(np.clip(sum(1 for x in st.rolling_evictions if x) / 10.0, 0.0, 1.0))

        return np.array(
            [
                cache_occupancy,
                latency_norm,
                payload_norm,
                anomaly,
                hit_rate_recent,
                stream_request_freq,
                time_since_last_request_s,
                cache_pressure,
            ],
            dtype=np.float32,
        )

    def update(self, node_id: str, telemetry_msg: EdgeTelemetry) -> None:
        """
        Updates rolling stats after observing a transition outcome (telemetry).
        """
        st = self._ensure(node_id)
        st.rolling_hits.append(bool(telemetry_msg.cache_hit))
        st.rolling_requests.append(str(telemetry_msg.stream_id))
        st.rolling_evictions.append(bool(getattr(telemetry_msg, "evicted", False)))
        st.last_request_time = time.time()

