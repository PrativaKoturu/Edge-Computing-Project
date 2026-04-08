from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class EdgeTelemetry:
    node_id: str
    ts_ms: int
    cache_hit: bool
    latency_ms: int
    stream_id: str
    cache_items: int
    payload_kb: int
    anomaly: bool
    cache_decision: bool
    evicted: bool
    score_int32: int

    @staticmethod
    def from_json(payload: str) -> "EdgeTelemetry":
        d = json.loads(payload)
        return EdgeTelemetry(
            node_id=str(d["node_id"]),
            ts_ms=int(d["ts_ms"]),
            cache_hit=bool(d["cache_hit"]),
            latency_ms=int(d["latency_ms"]),
            stream_id=str(d["stream_id"]),
            cache_items=int(d.get("cache_items", 0)),
            payload_kb=int(d.get("payload_kb", 0)),
            anomaly=bool(d.get("anomaly", False)),
            cache_decision=bool(d.get("cache_decision", False)),
            evicted=bool(d.get("evicted", False)),
            score_int32=int(d.get("score_int32", 0)),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


@dataclass(frozen=True)
class EdgeRequest:
    node_id: str
    ts_ms: int
    stream_id: str
    payload_kb: int
    anomaly: bool

    @staticmethod
    def from_json(payload: str) -> "EdgeRequest":
        d = json.loads(payload)
        return EdgeRequest(
            node_id=str(d["node_id"]),
            ts_ms=int(d["ts_ms"]),
            stream_id=str(d["stream_id"]),
            payload_kb=int(d["payload_kb"]),
            anomaly=bool(d["anomaly"]),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


@dataclass(frozen=True)
class PolicyUpdate:
    node_id: str
    ts_ms: int
    float_weights: list[float]
    int8_weights: list[int]

    @staticmethod
    def from_json(payload: str) -> "PolicyUpdate":
        d: dict[str, Any] = json.loads(payload)
        return PolicyUpdate(
            node_id=str(d["node_id"]),
            ts_ms=int(d["ts_ms"]),
            float_weights=[float(x) for x in d.get("float_weights", d.get("weights", []))],
            int8_weights=[int(x) for x in d.get("int8_weights", [])],
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))
