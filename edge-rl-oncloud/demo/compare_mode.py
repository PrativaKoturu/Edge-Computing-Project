from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np
import torch

from control_plane.models import LtCActor


@dataclass
class Req:
    payload_kb: int
    anomaly: bool
    stream_id: str


class TinyEdgePolicy:
    """
    Simulates the ESP32 int8 8-weight dot-product inference.
    """

    def __init__(self, int8_weights: list[int], threshold: int = 0):
        if len(int8_weights) != 8:
            raise ValueError("int8_weights must be length 8")
        self.w = [int(x) for x in int8_weights]
        self.threshold = int(threshold)

    def score_int32(self, state_int8: list[int]) -> int:
        s = 0
        for i in range(8):
            s += int(self.w[i]) * int(state_int8[i])
        return int(s)

    def cache_score_0_1(self, score_int32: int) -> float:
        # Map dot product to [0,1] deterministically for comparison.
        # Normalization constant corresponds to max magnitude ~ 8*(127*127).
        denom = 8.0 * 127.0 * 127.0
        x = float(score_int32) / denom
        return 1.0 / (1.0 + math.exp(-4.0 * x))


class MiniEnv:
    """
    Minimal environment that tracks cache contents and rolling stats to build the same 8-D state
    used by the trainer, but locally for comparison.
    """

    def __init__(self) -> None:
        self.cache: list[str] = []
        self.cache_capacity = 64
        self.rolling_hits: list[bool] = []
        self.rolling_requests: list[str] = []
        self.rolling_evictions: list[bool] = []
        self.last_request_ms: int | None = None

    def _hit_rate_recent(self) -> float:
        w = self.rolling_hits[-10:]
        return float(sum(1 for x in w if x) / len(w)) if w else 0.0

    def _stream_freq(self, stream_id: str) -> float:
        w = self.rolling_requests[-20:]
        if not w:
            return 0.0
        c = sum(1 for x in w if x == stream_id)
        return float(np.clip(c / 20.0, 0.0, 1.0))

    def _cache_pressure(self) -> float:
        w = self.rolling_evictions[-10:]
        return float(sum(1 for x in w if x) / len(w)) if w else 0.0

    def build_state(self, cache_items: int, latency_ms: int, payload_kb: int, anomaly: bool, stream_id: str, now_ms: int) -> np.ndarray:
        cache_occupancy = float(np.clip(cache_items / 64.0, 0.0, 1.0))
        latency_norm = float(np.clip(latency_ms / 2000.0, 0.0, 1.0))
        payload_norm = float(np.clip(payload_kb / 2000.0, 0.0, 1.0))
        anomaly_flag = 1.0 if anomaly else 0.0
        hit_rate = self._hit_rate_recent()
        freq = self._stream_freq(stream_id)
        if self.last_request_ms is None:
            time_since = 1.0
        else:
            time_since = float(np.clip((now_ms - self.last_request_ms) / 30000.0, 0.0, 1.0))
        pressure = float(np.clip(self._cache_pressure(), 0.0, 1.0))
        return np.array([cache_occupancy, latency_norm, payload_norm, anomaly_flag, hit_rate, freq, time_since, pressure], dtype=np.float32)

    def state_to_int8(self, state: np.ndarray) -> list[int]:
        # Spec mapping to int values in 0..127 (or 0..127 for most; anomaly 0/127)
        out: list[int] = []
        out.append(int(np.clip(state[0] * 127.0, 0, 127)))
        out.append(int(np.clip(state[1] * 127.0, 0, 127)))
        out.append(int(np.clip(state[2] * 127.0, 0, 127)))
        out.append(127 if state[3] >= 0.5 else 0)
        out.append(int(np.clip(state[4] * 127.0, 0, 127)))
        out.append(int(np.clip(state[5] * 127.0, 0, 127)))
        out.append(int(np.clip(state[6] * 127.0, 0, 127)))
        out.append(int(np.clip(state[7] * 127.0, 0, 127)))
        return out

    def step(self, req: Req, cache_decision: bool, now_ms: int) -> tuple[bool, int, bool]:
        hit = req.stream_id in self.cache
        latency = 45 if hit else random.randint(800, 2000)
        evicted = False
        if (cache_decision or req.anomaly) and (req.stream_id not in self.cache):
            if len(self.cache) < self.cache_capacity:
                self.cache.append(req.stream_id)
            else:
                # Evict oldest (simple proxy for LRU here)
                self.cache.pop(0)
                self.cache.append(req.stream_id)
                evicted = True

        self.rolling_hits.append(hit)
        self.rolling_requests.append(req.stream_id)
        self.rolling_evictions.append(evicted)
        self.last_request_ms = now_ms
        return hit, latency, evicted


@torch.no_grad()
def quantize_from_actor(actor: LtCActor) -> tuple[list[float], list[int]]:
    W = actor.input_proj.weight.detach().cpu()  # (19, 8)
    U, S, Vh = torch.linalg.svd(W, full_matrices=False)
    compressed = (S[:8].unsqueeze(1) * Vh[:8]).mean(dim=1)
    maxabs = float(compressed.abs().max().item())
    if maxabs == 0.0:
        q = torch.zeros_like(compressed, dtype=torch.int32)
    else:
        q = (compressed / maxabs * 127.0).round().to(torch.int32).clamp(-128, 127)
    return compressed.to(torch.float32).tolist(), [int(x) for x in q.tolist()]


def main() -> None:
    random.seed(7)
    np.random.seed(7)
    torch.manual_seed(7)

    actor = LtCActor()
    actor.eval()

    float_w, int8_w = quantize_from_actor(actor)
    edge_policy = TinyEdgePolicy(int8_weights=int8_w, threshold=0)

    # Fixed 20 synthetic requests
    streams = [f"cnc-{i:02d}/{s}" for i in range(1, 11) for s in ["vibration", "temperature", "pressure"]]
    reqs: list[Req] = []
    for i in range(20):
        reqs.append(
            Req(
                payload_kb=random.randint(500, 2000),
                anomaly=(random.random() < 0.15),
                stream_id=random.choice(streams),
            )
        )

    env_cpu = MiniEnv()
    env_edge = MiniEnv()

    cpu_hits = 0
    edge_hits = 0
    cpu_lat = 0.0
    edge_lat = 0.0

    print("=== Compare Mode: CPU LTC vs Edge int8 dot-product ===")
    print(f"Quantized int8 weights: {int8_w}")
    print("")

    now_ms = 0
    for i, req in enumerate(reqs, start=1):
        now_ms += 1500  # synthetic time progression

        # CPU policy
        latency_probe = 1200  # the point of caching is to reduce this; use a nominal pre-action estimate
        s_cpu = env_cpu.build_state(cache_items=len(env_cpu.cache), latency_ms=latency_probe, payload_kb=req.payload_kb, anomaly=req.anomaly, stream_id=req.stream_id, now_ms=now_ms)
        a_cpu = float(actor(torch.tensor(s_cpu).unsqueeze(0)).squeeze().item())  # [0,1]
        cpu_decision = (a_cpu > 0.5) or req.anomaly
        cpu_hit, cpu_latency, _ = env_cpu.step(req, cache_decision=cpu_decision, now_ms=now_ms)

        # Edge policy
        s_edge = env_edge.build_state(cache_items=len(env_edge.cache), latency_ms=latency_probe, payload_kb=req.payload_kb, anomaly=req.anomaly, stream_id=req.stream_id, now_ms=now_ms)
        s_edge_i8 = env_edge.state_to_int8(s_edge)
        score_i32 = edge_policy.score_int32(s_edge_i8)
        a_edge = edge_policy.cache_score_0_1(score_i32)
        edge_decision = (score_i32 > edge_policy.threshold) or req.anomaly
        edge_hit, edge_latency, _ = env_edge.step(req, cache_decision=edge_decision, now_ms=now_ms)

        cpu_hits += 1 if cpu_hit else 0
        edge_hits += 1 if edge_hit else 0
        cpu_lat += cpu_latency
        edge_lat += edge_latency

        delta = abs(a_cpu - a_edge)
        print(f"[{i:02d}] stream={req.stream_id} kb={req.payload_kb} anom={int(req.anomaly)}")
        print(f"     state={np.round(s_cpu, 3).tolist()}")
        print(f"     CPU  : a={a_cpu:.4f} decision={int(cpu_decision)} hit={int(cpu_hit)} lat={cpu_latency}ms")
        print(f"     EDGE : score_i32={score_i32:+6d} a={a_edge:.4f} decision={int(edge_decision)} hit={int(edge_hit)} lat={edge_latency}ms")
        print(f"     delta|a|={delta:.4f}")

    print("\n=== Aggregate ===")
    print(f"CPU  hit_rate={cpu_hits/20.0:.2f} avg_latency={cpu_lat/20.0:.1f}ms")
    print(f"EDGE hit_rate={edge_hits/20.0:.2f} avg_latency={edge_lat/20.0:.1f}ms")
    print(f"Tradeoff (EDGE - CPU): hit_rate={edge_hits/20.0 - cpu_hits/20.0:+.2f}, avg_latency={edge_lat/20.0 - cpu_lat/20.0:+.1f}ms")


if __name__ == "__main__":
    main()

