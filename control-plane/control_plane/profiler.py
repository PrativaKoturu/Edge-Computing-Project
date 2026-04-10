"""
Hardware profiling and benchmarking module.
Tracks CPU, memory, latency, and throughput metrics.
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from collections import defaultdict, deque
import psutil
import torch


@dataclass
class TimingBucket:
    """Tracks timing statistics for a named operation."""
    name: str
    times_ms: deque = field(default_factory=lambda: deque(maxlen=100))

    def record(self, ms: float) -> None:
        self.times_ms.append(ms)

    def stats(self) -> dict:
        if not self.times_ms:
            return {"name": self.name, "count": 0}
        times = list(self.times_ms)
        import statistics
        return {
            "name": self.name,
            "count": len(times),
            "mean_ms": statistics.mean(times),
            "min_ms": min(times),
            "max_ms": max(times),
            "stdev_ms": statistics.stdev(times) if len(times) > 1 else 0.0,
        }


@dataclass
class SystemMetrics:
    """Snapshot of system metrics at a point in time."""
    timestamp_s: float
    cpu_percent: float
    memory_mb: float
    memory_percent: float

    # Per-process if available
    process_metrics: dict[str, dict] = field(default_factory=dict)


@dataclass
class PerZoneMetrics:
    """Aggregated metrics for a single zone (zone-a or zone-b)."""
    zone_id: str
    requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_latency_ms: float = 0.0
    eviction_count: int = 0
    anomaly_count: int = 0

    def hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.requests if self.requests > 0 else 0.0


class SystemProfiler:
    """Monitors system-wide metrics (CPU, memory) in background thread."""

    def __init__(self, interval_s: float = 0.1) -> None:
        self.interval_s = interval_s
        self.metrics: list[SystemMetrics] = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _collect_loop(self) -> None:
        while self._running:
            try:
                metric = SystemMetrics(
                    timestamp_s=time.time(),
                    cpu_percent=psutil.cpu_percent(interval=0.05),
                    memory_mb=psutil.virtual_memory().used / (1024 ** 2),
                    memory_percent=psutil.virtual_memory().percent,
                )
                with self._lock:
                    self.metrics.append(metric)
            except Exception:
                pass
            time.sleep(self.interval_s)

    def stats(self) -> dict:
        """Return summary statistics."""
        with self._lock:
            if not self.metrics:
                return {"status": "no_data"}

            cpu_pcts = [m.cpu_percent for m in self.metrics]
            mem_mbs = [m.memory_mb for m in self.metrics]

            import statistics
            return {
                "samples": len(self.metrics),
                "cpu_mean_percent": statistics.mean(cpu_pcts),
                "cpu_max_percent": max(cpu_pcts),
                "memory_mean_mb": statistics.mean(mem_mbs),
                "memory_max_mb": max(mem_mbs),
                "memory_max_percent": max(m.memory_percent for m in self.metrics),
            }


class BenchmarkCollector:
    """Collects performance metrics across training."""

    def __init__(self) -> None:
        self.zone_metrics: dict[str, PerZoneMetrics] = {}
        self.timing_buckets: dict[str, TimingBucket] = {}
        self._lock = threading.Lock()
        self.system_profiler = SystemProfiler()

    def record_zone_telemetry(self, node_id: str, cache_hit: bool, latency_ms: int,
                             evicted: bool, anomaly: bool) -> None:
        """Record telemetry from an edge node."""
        with self._lock:
            if node_id not in self.zone_metrics:
                self.zone_metrics[node_id] = PerZoneMetrics(zone_id=node_id)

            m = self.zone_metrics[node_id]
            m.requests += 1
            if cache_hit:
                m.cache_hits += 1
            else:
                m.cache_misses += 1
            m.total_latency_ms += latency_ms
            if evicted:
                m.eviction_count += 1
            if anomaly:
                m.anomaly_count += 1

    def record_timing(self, operation: str, ms: float) -> None:
        """Record timing for an operation (inference, update, etc)."""
        with self._lock:
            if operation not in self.timing_buckets:
                self.timing_buckets[operation] = TimingBucket(name=operation)
            self.timing_buckets[operation].record(ms)

    def report(self) -> dict:
        """Generate comprehensive report."""
        with self._lock:
            zone_reports = {}
            for node_id, metrics in self.zone_metrics.items():
                zone_reports[node_id] = {
                    "requests": metrics.requests,
                    "cache_hits": metrics.cache_hits,
                    "cache_misses": metrics.cache_misses,
                    "hit_rate": f"{metrics.hit_rate():.3f}",
                    "avg_latency_ms": f"{metrics.avg_latency_ms():.1f}",
                    "eviction_count": metrics.eviction_count,
                    "anomaly_count": metrics.anomaly_count,
                }

            timing_reports = {}
            for op, bucket in self.timing_buckets.items():
                timing_reports[op] = bucket.stats()

            system_stats = self.system_profiler.stats()

            return {
                "zones": zone_reports,
                "timing": timing_reports,
                "system": system_stats,
            }


def get_device_info() -> dict:
    """Get information about available compute devices."""
    info = {
        "pytorch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cpu_count": psutil.cpu_count(logical=False),
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "total_memory_gb": psutil.virtual_memory().total / (1024 ** 3),
    }

    if torch.cuda.is_available():
        info["cuda_devices"] = torch.cuda.device_count()
        info["current_device"] = torch.cuda.current_device()
        info["cuda_device_name"] = torch.cuda.get_device_name(0)
        try:
            info["cuda_capability"] = torch.cuda.get_device_capability(0)
        except Exception:
            pass

    return info
