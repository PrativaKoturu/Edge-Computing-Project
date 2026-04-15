#!/usr/bin/env python3
"""
Real-Time Latency Monitor - Edge RL On-Cloud vs On-Device
==========================================================

Connects to both MQTT brokers and displays latency comparison in real-time.
Calculates min, max, average, and percentile latencies.

Usage:
  python3 latency_monitor.py

Output shows:
  - Live latency stream from both pipelines
  - Real-time statistics (avg, min, max, p50, p95, p99)
  - Message count and connection status
"""

import paho.mqtt.client as mqtt
import json
import time
from collections import deque
from datetime import datetime
import sys
import statistics
import os
import argparse

def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None and v != "" else default


def parse_args():
    p = argparse.ArgumentParser(description="Real-time latency monitor for MQTT pipelines.")
    p.add_argument(
        "--mode",
        choices=["local", "public"],
        default=_env("LAT_MON_MODE", "local"),
        help="Broker mode. local=localhost dual brokers (11883/1883). public=broker.hivemq.com (1883).",
    )
    p.add_argument("--oncloud-host", default=_env("MQTT_BROKER_ONCLOUD", "localhost"))
    p.add_argument("--oncloud-port", type=int, default=int(_env("MQTT_PORT_ONCLOUD", "11883")))
    p.add_argument("--ondevice-host", default=_env("MQTT_BROKER_ONDEVICE", "localhost"))
    p.add_argument("--ondevice-port", type=int, default=int(_env("MQTT_PORT_ONDEVICE", "1883")))
    p.add_argument("--interval", type=int, default=int(_env("LAT_MON_INTERVAL", "10")), help="Stats refresh seconds.")
    return p.parse_args()

# Data storage (keep last 1000 latencies per pipeline)
latencies = {
    "oncloud": deque(maxlen=1000),
    "ondevice": deque(maxlen=1000)
}

message_counts = {
    "oncloud": {"requests": 0, "telemetry": 0, "policy": 0},
    "ondevice": {"requests": 0, "telemetry": 0, "policy": 0}
}

connection_status = {
    "oncloud": False,
    "ondevice": False
}

# ─────────────────────────────────────────────────────────────────────────────
# MQTT Setup
# ─────────────────────────────────────────────────────────────────────────────

def create_callbacks(pipeline):
    """Create MQTT callbacks for a specific pipeline"""
    
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            connection_status[pipeline] = True
            # Subscribe to all relevant topics so counts and stats match reality.
            client.subscribe("edge/+/request", qos=0)
            client.subscribe("edge/+/telemetry", qos=0)
            client.subscribe("edge/+/policy", qos=0)
            print(f"✅ Connected to {pipeline.upper()} MQTT broker")
        else:
            print(f"❌ Failed to connect to {pipeline.upper()} (rc={rc})")
    
    def on_disconnect(client, userdata, rc):
        connection_status[pipeline] = False
        if rc != 0:
            print(f"⚠️  Disconnected from {pipeline.upper()} (rc={rc})")
    
    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            
            # Extract latency from telemetry
            if "latency_ms" in payload:
                latency = payload["latency_ms"]
                latencies[pipeline].append(latency)
                message_counts[pipeline]["telemetry"] += 1
                
                # Print individual message
                stream_id = payload.get("stream_id", "unknown")
                cache_hit = "HIT" if payload.get("cache_hit", False) else "MISS"
                print(f"  [{pipeline.upper()}] {stream_id}: {latency:.2f}ms ({cache_hit})")
            
            # Count message types
            if "/request" in msg.topic:
                message_counts[pipeline]["requests"] += 1
            elif "/policy" in msg.topic:
                message_counts[pipeline]["policy"] += 1
                
        except json.JSONDecodeError:
            pass
    
    return on_connect, on_disconnect, on_message


# ─────────────────────────────────────────────────────────────────────────────
# Statistics Calculation
# ─────────────────────────────────────────────────────────────────────────────

def calculate_stats(pipeline):
    """Calculate latency statistics for a pipeline"""
    if not latencies[pipeline]:
        return None
    
    data = list(latencies[pipeline])
    data_sorted = sorted(data)
    
    stats = {
        "count": len(data),
        "min": min(data),
        "max": max(data),
        "avg": statistics.mean(data),
        "median": statistics.median(data),
        "stdev": statistics.stdev(data) if len(data) > 1 else 0,
    }
    
    # Percentiles
    if len(data) >= 20:
        stats["p50"] = data_sorted[int(len(data) * 0.50)]
        stats["p95"] = data_sorted[int(len(data) * 0.95)]
        stats["p99"] = data_sorted[int(len(data) * 0.99)]
    else:
        stats["p50"] = stats["p95"] = stats["p99"] = stats["avg"]
    
    return stats


def print_stats():
    """Print formatted statistics"""
    print("\n" + "=" * 80)
    print(f"LATENCY STATISTICS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    for pipeline in ["oncloud", "ondevice"]:
        label = "ON-CLOUD" if pipeline == "oncloud" else "ON-DEVICE"
        print(f"\n{label}")
        print("-" * 40)
        
        # Connection status
        status = "🟢 CONNECTED" if connection_status[pipeline] else "🔴 DISCONNECTED"
        print(f"Status:    {status}")
        
        # Message counts
        counts = message_counts[pipeline]
        print(f"Messages:  {counts['telemetry']} telemetry, {counts['requests']} requests, {counts['policy']} policies")
        
        # Statistics
        stats = calculate_stats(pipeline)
        if stats:
            print(f"\nLatency Metrics (ms):")
            print(f"  Min:     {stats['min']:.2f} ms")
            print(f"  Max:     {stats['max']:.2f} ms")
            print(f"  Avg:     {stats['avg']:.2f} ms")
            print(f"  Median:  {stats['median']:.2f} ms")
            print(f"  Stdev:   {stats['stdev']:.2f} ms")
            print(f"  P50:     {stats['p50']:.2f} ms")
            print(f"  P95:     {stats['p95']:.2f} ms")
            print(f"  P99:     {stats['p99']:.2f} ms")
            print(f"  Count:   {stats['count']} samples")
        else:
            print("  No latency data yet...")


def print_comparison():
    """Print side-by-side comparison"""
    print("\n" + "=" * 80)
    print("LATENCY COMPARISON")
    print("=" * 80)
    
    stats_oncloud = calculate_stats("oncloud")
    stats_ondevice = calculate_stats("ondevice")
    
    if not stats_oncloud or not stats_ondevice:
        print("Waiting for data from both pipelines...")
        return
    
    print(f"\n{'Metric':<15} {'On-Cloud':<20} {'On-Device':<20} {'Difference':<20}")
    print("-" * 75)
    
    metrics = [
        ("Min (ms)", stats_oncloud["min"], stats_ondevice["min"]),
        ("Max (ms)", stats_oncloud["max"], stats_ondevice["max"]),
        ("Avg (ms)", stats_oncloud["avg"], stats_ondevice["avg"]),
        ("Median (ms)", stats_oncloud["median"], stats_ondevice["median"]),
        ("Stdev (ms)", stats_oncloud["stdev"], stats_ondevice["stdev"]),
        ("P95 (ms)", stats_oncloud["p95"], stats_ondevice["p95"]),
        ("P99 (ms)", stats_oncloud["p99"], stats_ondevice["p99"]),
    ]
    
    for metric, oncloud, ondevice in metrics:
        diff = ondevice - oncloud
        diff_str = f"{diff:+.2f}" if diff != 0 else "0.00"
        print(f"{metric:<15} {oncloud:>18.2f}  {ondevice:>18.2f}  {diff_str:>18}")
    
    # Overall assessment
    print("\n" + "-" * 75)
    avg_diff = stats_ondevice["avg"] - stats_oncloud["avg"]
    if abs(avg_diff) < 5:
        assessment = "✅ Similar performance (network-dominated)"
    elif avg_diff < 0:
        assessment = "⚡ On-Device faster"
    else:
        assessment = "☁️  On-Cloud faster"
    
    speedup = stats_oncloud["avg"] / stats_ondevice["avg"] if stats_ondevice["avg"] > 0 else 1
    print(f"Assessment: {assessment} (Speedup: {speedup:.2f}x)")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Main monitoring loop"""
    args = parse_args()

    if args.mode == "public":
        # Wokwi simulations use the public broker by default.
        args.oncloud_host = "broker.hivemq.com"
        args.oncloud_port = 1883
        args.ondevice_host = "broker.hivemq.com"
        args.ondevice_port = 1883

    print("🚀 Starting Latency Monitor...")
    print(f"   On-Cloud:  {args.oncloud_host}:{args.oncloud_port}")
    print(f"   On-Device: {args.ondevice_host}:{args.ondevice_port}")
    print("\n⏳ Waiting for MQTT connections...\n")
    
    # Create clients
    # Add PID suffix to avoid client_id collisions (broker will kick duplicates).
    pid_suffix = str(os.getpid())
    client_oncloud = mqtt.Client(client_id=f"latency-monitor-oncloud-{pid_suffix}")
    client_ondevice = mqtt.Client(client_id=f"latency-monitor-ondevice-{pid_suffix}")

    # Backoff reconnect attempts when brokers flap.
    client_oncloud.reconnect_delay_set(min_delay=1, max_delay=30)
    client_ondevice.reconnect_delay_set(min_delay=1, max_delay=30)
    
    # Setup callbacks
    on_connect_oc, on_disconnect_oc, on_message_oc = create_callbacks("oncloud")
    on_connect_od, on_disconnect_od, on_message_od = create_callbacks("ondevice")
    
    client_oncloud.on_connect = on_connect_oc
    client_oncloud.on_disconnect = on_disconnect_oc
    client_oncloud.on_message = on_message_oc
    
    client_ondevice.on_connect = on_connect_od
    client_ondevice.on_disconnect = on_disconnect_od
    client_ondevice.on_message = on_message_od
    
    # Connect
    try:
        client_oncloud.connect(args.oncloud_host, args.oncloud_port, keepalive=60)
        client_oncloud.loop_start()
    except Exception as e:
        print(f"❌ Failed to connect to on-cloud broker: {e}")
    
    try:
        client_ondevice.connect(args.ondevice_host, args.ondevice_port, keepalive=60)
        client_ondevice.loop_start()
    except Exception as e:
        print(f"❌ Failed to connect to on-device broker: {e}")
    
    # Print stats every 10 seconds
    try:
        while True:
            time.sleep(args.interval)
            print_stats()
            print_comparison()
            print("\n⏳ Monitoring... (Press Ctrl+C to exit)\n")
    
    except KeyboardInterrupt:
        print("\n\n📊 FINAL RESULTS")
        print_stats()
        print_comparison()
        
        # Cleanup
        client_oncloud.loop_stop()
        client_ondevice.loop_stop()
        client_oncloud.disconnect()
        client_ondevice.disconnect()
        
        print("\n✅ Monitor stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()
