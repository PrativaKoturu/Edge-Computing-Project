"""
Hardware Benchmark: CPU vs GPU vs Edge Simulator

Shows performance differences:
- Full TD3+LTC policy on CPU
- Full TD3+LTC policy on GPU (if available)
- Quantized int8 edge policy (simulated on CPU)
- Zone A vs Zone B metrics
"""

from __future__ import annotations

import sys
import time
import random
from pathlib import Path
from typing import NamedTuple

import numpy as np
import torch

# Add control plane to path
sys.path.insert(0, str(Path(__file__).parent.parent / "control-plane"))
sys.path.insert(0, str(Path(__file__).parent))

from control_plane.models import LtCActor, Td3Agent
from control_plane.profiler import get_device_info, BenchmarkCollector
from compare_mode import TinyEdgePolicy, MiniEnv, Req, quantize_from_actor


class BenchmarkResult(NamedTuple):
    """Results from a single benchmark run."""
    device: str
    policy_type: str  # "cpu_td3", "gpu_td3", "edge_int8"
    inference_times_ms: list[float]
    mean_inference_ms: float
    std_inference_ms: float
    min_inference_ms: float
    max_inference_ms: float


def benchmark_cpu_policy(actor: LtCActor, num_runs: int = 1000) -> BenchmarkResult:
    """Benchmark full TD3+LTC on CPU."""
    actor = actor.to(torch.device("cpu"))
    actor.eval()

    times_ms = []
    for _ in range(num_runs):
        state = torch.randn(1, 8, device=torch.device("cpu"))
        t0 = time.perf_counter()
        with torch.no_grad():
            _ = actor(state)
        t1 = time.perf_counter()
        times_ms.append((t1 - t0) * 1000)

    times_arr = np.array(times_ms)
    return BenchmarkResult(
        device="CPU",
        policy_type="cpu_td3",
        inference_times_ms=times_ms,
        mean_inference_ms=float(np.mean(times_arr)),
        std_inference_ms=float(np.std(times_arr)),
        min_inference_ms=float(np.min(times_arr)),
        max_inference_ms=float(np.max(times_arr)),
    )


def benchmark_gpu_policy(actor: LtCActor, num_runs: int = 1000) -> BenchmarkResult | None:
    """Benchmark full TD3+LTC on GPU (if available)."""
    if not torch.cuda.is_available():
        return None

    device = torch.device("cuda:0")
    actor = actor.to(device)
    actor.eval()

    # Warmup
    for _ in range(10):
        state = torch.randn(1, 8, device=device)
        with torch.no_grad():
            _ = actor(state)
    torch.cuda.synchronize()

    times_ms = []
    for _ in range(num_runs):
        state = torch.randn(1, 8, device=device)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            _ = actor(state)
        torch.cuda.synchronize()
        t1 = time.perf_counter()
        times_ms.append((t1 - t0) * 1000)

    times_arr = np.array(times_ms)
    return BenchmarkResult(
        device="GPU",
        policy_type="gpu_td3",
        inference_times_ms=times_ms,
        mean_inference_ms=float(np.mean(times_arr)),
        std_inference_ms=float(np.std(times_arr)),
        min_inference_ms=float(np.min(times_arr)),
        max_inference_ms=float(np.max(times_arr)),
    )


def benchmark_edge_policy(edge_policy: TinyEdgePolicy, num_runs: int = 1000) -> BenchmarkResult:
    """Benchmark int8 edge policy (simulated dot product)."""
    times_ms = []
    for _ in range(num_runs):
        # Random int8 state
        state_i8 = [random.randint(-128, 127) for _ in range(8)]
        t0 = time.perf_counter()
        _ = edge_policy.score_int32(state_i8)
        t1 = time.perf_counter()
        times_ms.append((t1 - t0) * 1000)

    times_arr = np.array(times_ms)
    return BenchmarkResult(
        device="CPU (simulated)",
        policy_type="edge_int8",
        inference_times_ms=times_ms,
        mean_inference_ms=float(np.mean(times_arr)),
        std_inference_ms=float(np.std(times_arr)),
        min_inference_ms=float(np.min(times_arr)),
        max_inference_ms=float(np.max(times_arr)),
    )


def zone_simulation(env_id: str, actor: LtCActor, edge_policy: TinyEdgePolicy,
                   num_requests: int = 100) -> dict:
    """Simulate a single zone (A or B) performance."""
    random.seed(42 + hash(env_id) % 1000)
    np.random.seed(42 + hash(env_id) % 1000)

    streams = [f"cnc-{i:02d}/{s}" for i in range(1, 26) for s in ["vibration", "temperature", "pressure"]]
    reqs = [
        Req(
            payload_kb=random.randint(500, 2000),
            anomaly=(random.random() < 0.15),
            stream_id=random.choice(streams),
        )
        for _ in range(num_requests)
    ]

    env_cpu = MiniEnv()
    env_edge = MiniEnv()

    cpu_hits = 0
    cpu_total_lat = 0.0
    edge_hits = 0
    edge_total_lat = 0.0

    cpu_times = []
    edge_times = []

    now_ms = 0
    for req in reqs:
        now_ms += 1500

        # CPU policy
        t0 = time.perf_counter()
        s_cpu = env_cpu.build_state(
            cache_items=len(env_cpu.cache),
            latency_ms=1200,
            payload_kb=req.payload_kb,
            anomaly=req.anomaly,
            stream_id=req.stream_id,
            now_ms=now_ms,
        )
        with torch.no_grad():
            a_cpu = float(actor(torch.tensor(s_cpu).unsqueeze(0)).squeeze().item())
        cpu_times.append((time.perf_counter() - t0) * 1000)
        cpu_decision = (a_cpu > 0.5) or req.anomaly
        cpu_hit, cpu_latency, _ = env_cpu.step(req, cache_decision=cpu_decision, now_ms=now_ms)
        cpu_hits += 1 if cpu_hit else 0
        cpu_total_lat += cpu_latency

        # Edge policy
        t0 = time.perf_counter()
        s_edge = env_edge.build_state(
            cache_items=len(env_edge.cache),
            latency_ms=1200,
            payload_kb=req.payload_kb,
            anomaly=req.anomaly,
            stream_id=req.stream_id,
            now_ms=now_ms,
        )
        s_edge_i8 = env_edge.state_to_int8(s_edge)
        score_i32 = edge_policy.score_int32(s_edge_i8)
        edge_times.append((time.perf_counter() - t0) * 1000)
        edge_decision = (score_i32 > edge_policy.threshold) or req.anomaly
        edge_hit, edge_latency, _ = env_edge.step(req, cache_decision=edge_decision, now_ms=now_ms)
        edge_hits += 1 if edge_hit else 0
        edge_total_lat += edge_latency

    return {
        "zone": env_id,
        "requests": num_requests,
        "cpu": {
            "hit_rate": cpu_hits / num_requests,
            "avg_latency_ms": cpu_total_lat / num_requests,
            "inference_time_mean_us": np.mean(cpu_times) * 1000,
            "inference_time_max_us": np.max(cpu_times) * 1000,
        },
        "edge": {
            "hit_rate": edge_hits / num_requests,
            "avg_latency_ms": edge_total_lat / num_requests,
            "inference_time_mean_us": np.mean(edge_times) * 1000,
            "inference_time_max_us": np.max(edge_times) * 1000,
        },
        "tradeoff": {
            "hit_rate_diff": (edge_hits - cpu_hits) / num_requests,
            "latency_diff_ms": (edge_total_lat - cpu_total_lat) / num_requests,
        },
    }


def main() -> None:
    print("\n" + "=" * 80)
    print("HARDWARE BENCHMARK: CPU vs GPU vs Edge Simulator")
    print("=" * 80 + "\n")

    # Device info
    device_info = get_device_info()
    print("System Configuration:")
    print(f"  PyTorch: {device_info['pytorch_version']}")
    print(f"  CPU cores (physical): {device_info['cpu_count']}")
    print(f"  CPU cores (logical): {device_info['logical_cpu_count']}")
    print(f"  Total memory: {device_info['total_memory_gb']:.1f} GB")
    if device_info["cuda_available"]:
        print(f"  GPU available: {device_info['cuda_device_name']}")
        print(f"  GPU compute capability: {device_info.get('cuda_capability')}")
    else:
        print("  GPU: Not available")
    print()

    # Initialize policies
    random.seed(7)
    np.random.seed(7)
    torch.manual_seed(7)

    actor = LtCActor()
    actor.eval()

    float_w, int8_w = quantize_from_actor(actor)
    edge_policy = TinyEdgePolicy(int8_weights=int8_w, threshold=0)

    # Run benchmarks
    print("=" * 80)
    print("1. INFERENCE TIME BENCHMARK (1000 runs)")
    print("=" * 80 + "\n")

    results = []

    print("Benchmarking CPU TD3+LTC policy...")
    cpu_result = benchmark_cpu_policy(actor, num_runs=1000)
    results.append(cpu_result)
    print(f"  Mean: {cpu_result.mean_inference_ms:.3f} ms")
    print(f"  Std:  {cpu_result.std_inference_ms:.3f} ms")
    print(f"  Min:  {cpu_result.min_inference_ms:.3f} ms")
    print(f"  Max:  {cpu_result.max_inference_ms:.3f} ms")
    print()

    if torch.cuda.is_available():
        print("Benchmarking GPU TD3+LTC policy...")
        gpu_result = benchmark_gpu_policy(actor, num_runs=1000)
        if gpu_result:
            results.append(gpu_result)
            speedup = cpu_result.mean_inference_ms / gpu_result.mean_inference_ms
            print(f"  Mean: {gpu_result.mean_inference_ms:.3f} ms")
            print(f"  Std:  {gpu_result.std_inference_ms:.3f} ms")
            print(f"  Min:  {gpu_result.min_inference_ms:.3f} ms")
            print(f"  Max:  {gpu_result.max_inference_ms:.3f} ms")
            print(f"  Speedup vs CPU: {speedup:.1f}x")
        print()
    else:
        print("GPU not available, skipping GPU benchmark\n")

    print("Benchmarking Edge int8 policy (simulated)...")
    edge_result = benchmark_edge_policy(edge_policy, num_runs=1000)
    results.append(edge_result)
    speedup_vs_cpu = cpu_result.mean_inference_ms / edge_result.mean_inference_ms
    print(f"  Mean: {edge_result.mean_inference_ms:.4f} ms ({edge_result.mean_inference_ms * 1000:.2f} µs)")
    print(f"  Std:  {edge_result.std_inference_ms:.4f} ms")
    print(f"  Min:  {edge_result.min_inference_ms:.4f} ms")
    print(f"  Max:  {edge_result.max_inference_ms:.4f} ms")
    print(f"  Speedup vs CPU: {speedup_vs_cpu:.1f}x")
    print()

    # Zone simulation
    print("=" * 80)
    print("2. ZONE A vs ZONE B CACHING PERFORMANCE (100 requests each)")
    print("=" * 80 + "\n")

    zone_a = zone_simulation("zone-a", actor, edge_policy, num_requests=100)
    zone_b = zone_simulation("zone-b", actor, edge_policy, num_requests=100)

    for zone_data in [zone_a, zone_b]:
        print(f"{zone_data['zone'].upper()}:")
        print(f"  Requests: {zone_data['requests']}")
        print()
        print(f"  CPU Policy:")
        print(f"    Hit rate: {zone_data['cpu']['hit_rate']:.2%}")
        print(f"    Avg latency: {zone_data['cpu']['avg_latency_ms']:.1f} ms")
        print(f"    Inference: {zone_data['cpu']['inference_time_mean_us']:.2f} µs (avg)")
        print()
        print(f"  Edge Policy:")
        print(f"    Hit rate: {zone_data['edge']['hit_rate']:.2%}")
        print(f"    Avg latency: {zone_data['edge']['avg_latency_ms']:.1f} ms")
        print(f"    Inference: {zone_data['edge']['inference_time_mean_us']:.2f} µs (avg)")
        print()
        print(f"  Tradeoff (Edge vs CPU):")
        print(f"    Hit rate delta: {zone_data['tradeoff']['hit_rate_diff']:+.2%}")
        print(f"    Latency delta: {zone_data['tradeoff']['latency_diff_ms']:+.1f} ms")
        print()

    # Summary comparison
    print("=" * 80)
    print("3. SUMMARY: FULL SYSTEM COMPARISON")
    print("=" * 80 + "\n")

    print("Inference Speed Comparison:")
    print(f"  CPU TD3+LTC:          {cpu_result.mean_inference_ms:8.3f} ms per inference")
    if torch.cuda.is_available() and gpu_result:
        print(f"  GPU TD3+LTC:          {gpu_result.mean_inference_ms:8.3f} ms per inference")
        print(f"  GPU Speedup:          {speedup:8.1f}x faster")
    print(f"  Edge int8 (simulated): {edge_result.mean_inference_ms:8.4f} ms per inference ({edge_result.mean_inference_ms * 1000:.2f} µs)")
    print(f"  Edge Speedup:         {speedup_vs_cpu:8.1f}x faster than CPU")
    print()

    print("Deployment Scenario Summary:")
    print(f"  CPU execution: Best for trainer/central policy. Slow for edge (~{cpu_result.mean_inference_ms:.1f} ms/req)")
    if torch.cuda.is_available() and gpu_result:
        gpu_speedup = cpu_result.mean_inference_ms / gpu_result.mean_inference_ms
        print(f"  GPU execution: {gpu_speedup:.1f}x faster training if available. Not suitable for ESP32 edge.")
    print(f"  Edge int8:     Deployed on ESP32. Ultra-fast (~{edge_result.mean_inference_ms * 1000:.1f} µs), quantized quality loss.")
    print()

    print("Zone Performance Parity:")
    cpu_avg_hit = (zone_a['cpu']['hit_rate'] + zone_b['cpu']['hit_rate']) / 2
    edge_avg_hit = (zone_a['edge']['hit_rate'] + zone_b['edge']['hit_rate']) / 2
    print(f"  CPU hit rate (avg A&B): {cpu_avg_hit:.2%}")
    print(f"  Edge hit rate (avg A&B): {edge_avg_hit:.2%}")
    print(f"  Zone isolation: Zones maintain independent cache state and rolling stats")
    print()

    print("=" * 80)
    print("BENCHMARK COMPLETE")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
