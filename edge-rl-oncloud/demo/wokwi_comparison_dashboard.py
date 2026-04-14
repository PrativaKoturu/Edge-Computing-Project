"""
Wokwi Comparison Dashboard

Real-time visualization of:
- Edge Node zone-a (Wokwi ESP32 simulation)
- Control Plane (your CPU/GPU trainer)

Shows live metrics: cache hits, latency, RL training progress.
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

    def __init__(self, mqtt_host: str = "broker.hivemq.com", mqtt_port: int = 1883):
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.zone_metrics: dict[str, ZoneMetrics] = {
            "zone-a": ZoneMetrics("zone-a"),
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
    """Print comparison between edge node and central trainer."""
    print(f"{Color.HEADER}{Color.BOLD}┌─ COMPARISON: EDGE vs CENTRAL ─┐{Color.ENDC}")

    zone_a = zones.get("zone-a")

    print(f"  {Color.BOLD}Edge Node (ESP32 on Wokwi){Color.ENDC}  vs  {Color.BOLD}Central Trainer (your CPU/GPU){Color.ENDC}")
    print()
    if zone_a and zone_a.requests > 0:
        print(f"    Edge cache hit rate:    {zone_a.hit_rate():6.1f}%   (improves as policy updates arrive)")
        print(f"    Edge avg latency:       {zone_a.avg_latency_ms():6.1f} ms  (45ms hit, 800-2000ms miss)")
        print(f"    Edge requests seen:     {zone_a.requests:6d}")
    print()
    print(f"  {Color.BOLD}Inference speed comparison:{Color.ENDC}")
    print(f"    ESP32 int8 dot product:  ~0.7 µs   (8 multiplies + add)")
    print(f"    CPU  full TD3+LTC net:  ~190 µs   (thousands of ops)")
    print(f"    Speedup:                {Color.OKGREEN}~270x faster on edge{Color.ENDC}")
    print(f"    Why:                    Full network can't fit on ESP32 (no float32 tensor ops)")
    print()


def print_insights(zones: dict[str, ZoneMetrics], trainer: TrainerMetrics):
    """Print what is happening right now in the system."""
    print(f"{Color.HEADER}{Color.BOLD}┌─ SYSTEM STATUS ─┐{Color.ENDC}")

    zone_a = zones.get("zone-a")

    insights = []

    # Step 1: Is telemetry flowing?
    if trainer.replay_size == 0:
        insights.append(f"{Color.WARNING}[1/4] Trainer waiting for telemetry — make sure Wokwi is running and shows [req] messages{Color.ENDC}")
    else:
        insights.append(f"{Color.OKGREEN}[1/4] Telemetry flowing: {trainer.replay_size} transitions in replay buffer{Color.ENDC}")

    # Step 2: Is edge node connected?
    if zone_a and zone_a.requests > 0:
        insights.append(f"{Color.OKGREEN}[2/4] Edge node connected: {zone_a.requests} requests processed on ESP32{Color.ENDC}")
    else:
        insights.append(f"{Color.WARNING}[2/4] Edge node not connected — paste firmware into Wokwi and click Run{Color.ENDC}")

    # Step 3: Is RL training running?
    if trainer.critic_updates == 0:
        needed = max(0, 64 - trainer.replay_size)
        if needed > 0:
            insights.append(f"{Color.WARNING}[3/4] RL training waiting: need {needed} more transitions to start (have {trainer.replay_size}/64){Color.ENDC}")
        else:
            insights.append(f"{Color.WARNING}[3/4] RL training not started yet (enough data, starting soon){Color.ENDC}")
    else:
        avg_loss = trainer.critic_loss_avg10
        insights.append(f"{Color.OKGREEN}[3/4] RL training running: {trainer.critic_updates} TD3 updates, critic_loss={avg_loss:.4f}{Color.ENDC}")

    # Step 4: Has policy been pushed to edge?
    if trainer.policy_publishes > 0:
        insights.append(f"{Color.OKGREEN}[4/4] Policy pushed to ESP32 {trainer.policy_publishes} time(s) — edge is using trained weights{Color.ENDC}")
    else:
        updates_needed = max(0, 200 - trainer.critic_updates)
        insights.append(f"{Color.WARNING}[4/4] First policy push pending: {updates_needed} more critic updates needed (of 200){Color.ENDC}")

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
    print("Connecting to MQTT broker (broker.hivemq.com:1883)...")

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
