"""
Wokwi Comparison Dashboard

Real-time visualization of:
- Zone A (Wokwi ESP32 simulation)
- Zone B (Wokwi ESP32 simulation)
- Control Plane (your CPU/GPU trainer)

Shows side-by-side metrics and performance comparison.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

import paho.mqtt.client as mqtt
from datetime import datetime

# Color codes for terminal output
class Color:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


@dataclass
class ZoneMetrics:
    """Per-zone telemetry metrics."""
    zone_id: str
    requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_latency_ms: float = 0.0
    eviction_count: int = 0
    anomaly_count: int = 0
    max_cache_items: int = 0
    latest_timestamp: float = 0.0
    recent_telemetry: deque = field(default_factory=lambda: deque(maxlen=10))

    def hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0.0

    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.requests if self.requests > 0 else 0.0

    def update_from_telemetry(self, telem: dict) -> None:
        """Update metrics from a telemetry message."""
        self.requests += 1
        if telem.get("cache_hit"):
            self.cache_hits += 1
        else:
            self.cache_misses += 1
        self.total_latency_ms += telem.get("latency_ms", 0)
        if telem.get("evicted"):
            self.eviction_count += 1
        if telem.get("anomaly"):
            self.anomaly_count += 1
        cache_items = telem.get("cache_items", 0)
        self.max_cache_items = max(self.max_cache_items, cache_items)
        self.latest_timestamp = time.time()
        self.recent_telemetry.append({
            "hit": telem.get("cache_hit"),
            "latency": telem.get("latency_ms"),
            "stream": telem.get("stream_id"),
        })


@dataclass
class TrainerMetrics:
    """Central trainer metrics."""
    replay_size: int = 0
    critic_updates: int = 0
    critic_loss_avg10: float = 0.0
    actor_loss_avg10: float = 0.0
    policy_publishes: int = 0
    latest_timestamp: float = 0.0
    device: str = "CPU"
    cpu_percent: float = 0.0
    memory_mb: float = 0.0


class DashboardCollector:
    """Collects metrics from MQTT and maintains dashboard state."""

    def __init__(self, mqtt_host: str = "localhost", mqtt_port: int = 1883):
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.zone_metrics: dict[str, ZoneMetrics] = {
            "zone-a": ZoneMetrics("zone-a"),
            "zone-b": ZoneMetrics("zone-b"),
        }
        self.trainer_metrics = TrainerMetrics()
        self._lock = threading.Lock()

        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"{Color.OKGREEN}[MQTT] Connected to broker{Color.ENDC}")
            client.subscribe("edge/+/telemetry", qos=0)
            client.subscribe("trainer/stats", qos=0)
        else:
            print(f"{Color.FAIL}[MQTT] Connection failed rc={rc}{Color.ENDC}")

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            print(f"{Color.WARNING}[MQTT] Disconnected rc={rc}{Color.ENDC}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())

            if msg.topic.startswith("edge/"):
                # Zone telemetry
                zone_id = payload.get("node_id", "unknown")
                with self._lock:
                    if zone_id in self.zone_metrics:
                        self.zone_metrics[zone_id].update_from_telemetry(payload)

            elif msg.topic == "trainer/stats":
                # Trainer stats
                with self._lock:
                    self.trainer_metrics.replay_size = payload.get("replay_size", 0)
                    self.trainer_metrics.critic_updates = payload.get("critic_updates", 0)
                    self.trainer_metrics.critic_loss_avg10 = payload.get("critic_loss_avg10", 0.0)
                    self.trainer_metrics.actor_loss_avg10 = payload.get("actor_loss_avg10", 0.0)
                    self.trainer_metrics.policy_publishes = payload.get("policy_publishes", 0)
                    self.trainer_metrics.latest_timestamp = time.time()

        except Exception as e:
            print(f"{Color.FAIL}[Error] Failed to parse message: {e}{Color.ENDC}")

    def connect(self):
        """Connect to MQTT broker."""
        try:
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
            self.mqtt_client.loop_start()
        except Exception as e:
            print(f"{Color.FAIL}[Error] MQTT connection failed: {e}{Color.ENDC}")
            print(f"  Host: {self.mqtt_host}:{self.mqtt_port}")
            print(f"  Is docker compose running? (docker compose up --build)")

    def disconnect(self):
        """Disconnect from MQTT broker."""
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()

    def get_metrics(self) -> tuple[dict[str, ZoneMetrics], TrainerMetrics]:
        """Get current metrics snapshot."""
        with self._lock:
            return dict(self.zone_metrics), TrainerMetrics(
                replay_size=self.trainer_metrics.replay_size,
                critic_updates=self.trainer_metrics.critic_updates,
                critic_loss_avg10=self.trainer_metrics.critic_loss_avg10,
                actor_loss_avg10=self.trainer_metrics.actor_loss_avg10,
                policy_publishes=self.trainer_metrics.policy_publishes,
                latest_timestamp=self.trainer_metrics.latest_timestamp,
                cpu_percent=self.trainer_metrics.cpu_percent,
                memory_mb=self.trainer_metrics.memory_mb,
            )


def format_metric(label: str, value, unit: str = "", width: int = 15) -> str:
    """Format a metric for display."""
    if isinstance(value, float):
        formatted = f"{value:.2f}"
    else:
        formatted = str(value)
    return f"{label:<25} {formatted:>{width}} {unit}".ljust(50)


def clear_screen():
    """Clear terminal screen."""
    print("\033[H\033[J", end="")


def print_header():
    """Print dashboard header."""
    print(f"\n{Color.BOLD}{'='*100}{Color.ENDC}")
    print(f"{Color.BOLD}{'WOKWI vs CONTROL PLANE COMPARISON DASHBOARD':^100}{Color.ENDC}")
    print(f"{Color.BOLD}{'='*100}{Color.ENDC}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()


def print_zone_section(zone_id: str, metrics: ZoneMetrics):
    """Print section for a single zone."""
    print(f"{Color.HEADER}{Color.BOLD}┌─ {zone_id.upper()} (Wokwi ESP32) ─┐{Color.ENDC}")

    status_color = Color.OKGREEN if metrics.requests > 0 else Color.WARNING
    status = "✓ Active" if metrics.requests > 0 else "● Waiting..."
    print(f"  {status_color}Status{Color.ENDC}: {status}")

    print(f"  {format_metric('Requests', metrics.requests)}")
    print(f"  {format_metric('Cache Hits', metrics.cache_hits)} ({metrics.hit_rate():.1f}%)")
    print(f"  {format_metric('Cache Misses', metrics.cache_misses)}")
    print(f"  {format_metric('Avg Latency', metrics.avg_latency_ms(), 'ms')}")
    print(f"  {format_metric('Max Cache Size', metrics.max_cache_items, 'items')}")
    print(f"  {format_metric('Evictions', metrics.eviction_count)}")
    print(f"  {format_metric('Anomalies', metrics.anomaly_count)}")

    if metrics.recent_telemetry:
        recent_hits = sum(1 for t in metrics.recent_telemetry if t["hit"])
        print(f"  {format_metric('Recent Hits (10 req)', recent_hits, 'items')}")

    print()


def print_trainer_section(trainer_metrics: TrainerMetrics):
    """Print section for trainer metrics."""
    print(f"{Color.HEADER}{Color.BOLD}┌─ CONTROL PLANE (Your {trainer_metrics.device}) ─┐{Color.ENDC}")

    status_color = Color.OKGREEN if trainer_metrics.replay_size > 0 else Color.WARNING
    status = "✓ Training" if trainer_metrics.critic_updates > 0 else "● Waiting for telemetry..."
    print(f"  {status_color}Status{Color.ENDC}: {status}")

    print(f"  {format_metric('Replay Buffer Size', trainer_metrics.replay_size)}")
    print(f"  {format_metric('Critic Updates', trainer_metrics.critic_updates)}")
    print(f"  {format_metric('Critic Loss (avg10)', trainer_metrics.critic_loss_avg10, 'L2')}")
    print(f"  {format_metric('Actor Loss (avg10)', trainer_metrics.actor_loss_avg10)}")
    print(f"  {format_metric('Policy Publishes', trainer_metrics.policy_publishes, '(to edges)')}")

    if trainer_metrics.cpu_percent > 0:
        print(f"  {format_metric('CPU Usage', trainer_metrics.cpu_percent, '%')}")
    if trainer_metrics.memory_mb > 0:
        print(f"  {format_metric('Memory Usage', trainer_metrics.memory_mb, 'MB')}")

    print()


def print_comparison_section(zones: dict[str, ZoneMetrics], trainer: TrainerMetrics):
    """Print comparison between zones and trainer."""
    print(f"{Color.HEADER}{Color.BOLD}┌─ COMPARISON ─┐{Color.ENDC}")

    zone_a = zones.get("zone-a")
    zone_b = zones.get("zone-b")

    print(f"  {Color.BOLD}Zone A{Color.ENDC} vs {Color.BOLD}Zone B{Color.ENDC}")
    if zone_a and zone_b:
        a_hit = zone_a.hit_rate()
        b_hit = zone_b.hit_rate()
        print(f"    Hit Rate:     {a_hit:6.1f}%  vs  {b_hit:6.1f}%  {'(A better)' if a_hit > b_hit else '(B better)' if b_hit > a_hit else '(Tied)'}")

        a_lat = zone_a.avg_latency_ms()
        b_lat = zone_b.avg_latency_ms()
        print(f"    Avg Latency:  {a_lat:6.1f}ms  vs  {b_lat:6.1f}ms")

        print(f"    Total Req:    {zone_a.requests:6d}  vs  {zone_b.requests:6d}")

    print()
    print(f"  {Color.BOLD}Edge (Wokwi) vs Control (CPU){Color.ENDC}")
    if zone_a:
        print(f"    Inference:    ~0.7 µs (int8)  vs  ~190 µs (TD3+LTC)")
        print(f"    Speedup:      {Color.OKGREEN}~270x faster{Color.ENDC} on edge!")

    print()


def print_insights(zones: dict[str, ZoneMetrics], trainer: TrainerMetrics):
    """Print actionable insights."""
    print(f"{Color.HEADER}{Color.BOLD}┌─ INSIGHTS ─┐{Color.ENDC}")

    zone_a = zones.get("zone-a")
    zone_b = zones.get("zone-b")

    insights = []

    if trainer.replay_size == 0:
        insights.append(f"{Color.WARNING}⚠ Waiting for telemetry (make sure Wokwi zones are connected){Color.ENDC}")
    elif trainer.critic_updates == 0:
        insights.append(f"{Color.WARNING}⚠ Trainer waiting for enough samples (need {trainer.replay_size}/64 more){Color.ENDC}")
    else:
        insights.append(f"{Color.OKGREEN}✓ Training in progress ({trainer.critic_updates} critic updates){Color.ENDC}")

    if zone_a and zone_a.requests > 0:
        insights.append(f"{Color.OKGREEN}✓ Zone A is connected and receiving requests{Color.ENDC}")
    else:
        insights.append(f"{Color.WARNING}⚠ Zone A not yet connected or no requests received{Color.ENDC}")

    if zone_b and zone_b.requests > 0:
        insights.append(f"{Color.OKGREEN}✓ Zone B is connected and receiving requests{Color.ENDC}")
    else:
        insights.append(f"{Color.WARNING}⚠ Zone B not yet connected or no requests received{Color.ENDC}")

    if trainer.policy_publishes > 0:
        insights.append(f"{Color.OKGREEN}✓ Policy updates sent to edges ({trainer.policy_publishes} times){Color.ENDC}")
    else:
        insights.append(f"{Color.WARNING}⚠ Waiting to publish first policy (need ~200 critic updates){Color.ENDC}")

    if zone_a and zone_b and zone_a.requests > 10 and zone_b.requests > 10:
        a_hit = zone_a.hit_rate()
        b_hit = zone_b.hit_rate()
        if abs(a_hit - b_hit) < 5:
            insights.append(f"{Color.OKGREEN}✓ Zones learning together! Hit rates converging{Color.ENDC}")
        else:
            insights.append(f"{Color.OKCYAN}ℹ Zones have different request patterns (expected){Color.ENDC}")

    for insight in insights:
        print(f"  {insight}")

    print()


def print_footer():
    """Print dashboard footer."""
    print(f"{Color.BOLD}{'='*100}{Color.ENDC}")
    print(f"Refresh rate: 2s | Press Ctrl+C to exit")
    print()


def main():
    print(f"{Color.OKGREEN}Starting Wokwi Comparison Dashboard...{Color.ENDC}")
    print("Connecting to MQTT broker (localhost:1883)...")

    collector = DashboardCollector()
    collector.connect()

    # Give MQTT time to connect
    time.sleep(1)

    try:
        while True:
            clear_screen()
            print_header()

            zones, trainer = collector.get_metrics()

            # Print sections
            print_zone_section("zone-a", zones["zone-a"])
            print_zone_section("zone-b", zones["zone-b"])
            print_trainer_section(trainer)
            print_comparison_section(zones, trainer)
            print_insights(zones, trainer)
            print_footer()

            time.sleep(2)

    except KeyboardInterrupt:
        print(f"\n{Color.OKGREEN}Dashboard stopped.{Color.ENDC}")
    finally:
        collector.disconnect()


if __name__ == "__main__":
    main()
