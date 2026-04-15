#!/usr/bin/env python3
"""
Dual Pipeline Test Suite
========================
Tests both edge-rl-oncloud and edge-rl-ondevice simultaneously.
Monitors MQTT connectivity, message flow, and latency metrics.
"""

import os
import sys
import time
import subprocess
import json
from datetime import datetime
from pathlib import Path
import paho.mqtt.client as mqtt
from collections import defaultdict
import signal

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent
ONCLOUD_DIR = PROJECT_ROOT / "edge-rl-oncloud"
ONDEVICE_DIR = PROJECT_ROOT / "edge-rl-ondevice"

MQTT_BROKER_ONCLOUD = "localhost"
MQTT_PORT_ONCLOUD = 11883  # Different port to avoid conflict
MQTT_BROKER_ONDEVICE = "localhost"
MQTT_PORT_ONDEVICE = 1883

TEST_DURATION_SECONDS = 120  # 2 minutes

# ─────────────────────────────────────────────────────────────────────────────
# Global State
# ─────────────────────────────────────────────────────────────────────────────

test_results = {
    "oncloud": {
        "mqtt_connected": False,
        "requests_received": 0,
        "responses_received": 0,
        "telemetry_received": 0,
        "policy_received": 0,
        "latencies": [],
        "errors": [],
        "start_time": None,
    },
    "ondevice": {
        "mqtt_connected": False,
        "requests_received": 0,
        "responses_received": 0,
        "telemetry_received": 0,
        "policy_received": 0,
        "latencies": [],
        "errors": [],
        "start_time": None,
    }
}

latency_tracker = {
    "oncloud": defaultdict(list),  # stream_id → [latencies]
    "ondevice": defaultdict(list),
}

# ─────────────────────────────────────────────────────────────────────────────
# MQTT Callbacks
# ─────────────────────────────────────────────────────────────────────────────

def create_mqtt_callbacks(pipeline):
    """Create callbacks for a specific pipeline (oncloud or ondevice)"""
    
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            test_results[pipeline]["mqtt_connected"] = True
            print(f"✅ {pipeline.upper()}: MQTT connected")
            client.subscribe(f"edge/+/request", qos=0)
            client.subscribe(f"edge/+/telemetry", qos=0)
            client.subscribe(f"edge/+/policy", qos=0)
        else:
            test_results[pipeline]["errors"].append(f"MQTT connection failed: rc={rc}")
            print(f"❌ {pipeline.upper()}: MQTT connection failed (rc={rc})")
    
    def on_disconnect(client, userdata, rc):
        if rc != 0:
            test_results[pipeline]["mqtt_connected"] = False
            msg = f"MQTT disconnected unexpectedly: rc={rc}"
            test_results[pipeline]["errors"].append(msg)
            print(f"⚠️  {pipeline.upper()}: {msg}")
    
    def on_message(client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            if "request" in topic:
                test_results[pipeline]["requests_received"] += 1
                stream_id = payload.get("stream_id", "unknown")
                print(f"📤 {pipeline.upper()}: Request #{test_results[pipeline]['requests_received']} - {stream_id}")
                
            elif "telemetry" in topic:
                test_results[pipeline]["telemetry_received"] += 1
                stream_id = payload.get("stream_id", "unknown")
                latency = payload.get("latency_ms", 0)
                latency_tracker[pipeline][stream_id].append(latency)
                test_results[pipeline]["latencies"].append(latency)
                hit = payload.get("cache_hit", False)
                print(f"📥 {pipeline.upper()}: Telemetry #{test_results[pipeline]['telemetry_received']} - {stream_id} (latency={latency}ms, hit={hit})")
                
            elif "policy" in topic:
                test_results[pipeline]["policy_received"] += 1
                print(f"🎯 {pipeline.upper()}: Policy update #{test_results[pipeline]['policy_received']} received")
                
        except json.JSONDecodeError:
            error = f"Invalid JSON in message on {msg.topic}"
            test_results[pipeline]["errors"].append(error)
            print(f"⚠️  {pipeline.upper()}: {error}")
        except Exception as e:
            error = f"Error processing message: {str(e)}"
            test_results[pipeline]["errors"].append(error)
            print(f"❌ {pipeline.upper()}: {error}")
    
    def on_subscribe(client, userdata, mid, granted_qos):
        print(f"✅ {pipeline.upper()}: Subscribed to topics")
    
    return on_connect, on_disconnect, on_message, on_subscribe


# ─────────────────────────────────────────────────────────────────────────────
# Docker Management
# ─────────────────────────────────────────────────────────────────────────────

def start_pipeline(pipeline):
    """Start a pipeline using docker-compose"""
    pipeline_dir = ONCLOUD_DIR if pipeline == "oncloud" else ONDEVICE_DIR
    
    print(f"\n📦 Starting {pipeline.upper()} pipeline...")
    try:
        # Update docker-compose.yml to use different ports if oncloud
        if pipeline == "oncloud":
            # Modify mosquitto port binding for oncloud to avoid conflict
            compose_file = pipeline_dir / "docker-compose.yml"
            with open(compose_file, 'r') as f:
                content = f.read()
            # Update port
            updated = content.replace('- "1883:1883"', f'- "{MQTT_PORT_ONCLOUD}:1883"')
            with open(compose_file, 'w') as f:
                f.write(updated)
        
        result = subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=pipeline_dir,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print(f"✅ {pipeline.upper()}: Docker containers started")
            time.sleep(5)  # Wait for services to be ready
            return True
        else:
            error = f"Docker compose failed: {result.stderr}"
            test_results[pipeline]["errors"].append(error)
            print(f"❌ {pipeline.upper()}: {error}")
            return False
            
    except subprocess.TimeoutExpired:
        error = "Docker compose timeout"
        test_results[pipeline]["errors"].append(error)
        print(f"❌ {pipeline.upper()}: {error}")
        return False
    except Exception as e:
        error = f"Error starting pipeline: {str(e)}"
        test_results[pipeline]["errors"].append(error)
        print(f"❌ {pipeline.upper()}: {error}")
        return False


def stop_pipeline(pipeline):
    """Stop a pipeline using docker-compose"""
    pipeline_dir = ONCLOUD_DIR if pipeline == "oncloud" else ONDEVICE_DIR
    
    print(f"\n🛑 Stopping {pipeline.upper()} pipeline...")
    try:
        result = subprocess.run(
            ["docker", "compose", "down"],
            cwd=pipeline_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print(f"✅ {pipeline.upper()}: Docker containers stopped")
            return True
        else:
            print(f"⚠️  {pipeline.upper()}: Docker compose down had issues")
            return False
            
    except Exception as e:
        print(f"❌ {pipeline.upper()}: Error stopping pipeline: {str(e)}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# MQTT Monitoring
# ─────────────────────────────────────────────────────────────────────────────

def setup_mqtt_monitoring(pipeline):
    """Setup MQTT client for a pipeline"""
    broker = MQTT_BROKER_ONCLOUD if pipeline == "oncloud" else MQTT_BROKER_ONDEVICE
    port = MQTT_PORT_ONCLOUD if pipeline == "oncloud" else MQTT_PORT_ONDEVICE
    
    print(f"\n🔌 Setting up MQTT monitoring for {pipeline.upper()} (broker={broker}:{port})...")
    
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"test-{pipeline}")
        on_connect, on_disconnect, on_message, on_subscribe = create_mqtt_callbacks(pipeline)
        
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        client.on_subscribe = on_subscribe
        
        client.connect(broker, port, keepalive=60)
        client.loop_start()
        
        test_results[pipeline]["start_time"] = datetime.now()
        return client
        
    except Exception as e:
        error = f"MQTT setup failed: {str(e)}"
        test_results[pipeline]["errors"].append(error)
        print(f"❌ {pipeline.upper()}: {error}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Main Test
# ─────────────────────────────────────────────────────────────────────────────

def run_test():
    """Run the dual pipeline test"""
    
    print("\n" + "="*80)
    print("  DUAL PIPELINE TEST - Edge RL On-Cloud vs On-Device")
    print("="*80)
    print(f"Test Duration: {TEST_DURATION_SECONDS} seconds")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    clients = {}
    
    try:
        # Start both pipelines
        oncloud_ok = start_pipeline("oncloud")
        ondevice_ok = start_pipeline("ondevice")
        
        if not (oncloud_ok and ondevice_ok):
            print("\n❌ Failed to start one or both pipelines")
            return False
        
        # Setup MQTT monitoring
        clients["oncloud"] = setup_mqtt_monitoring("oncloud")
        clients["ondevice"] = setup_mqtt_monitoring("ondevice")
        
        if not (clients["oncloud"] and clients["ondevice"]):
            print("\n❌ Failed to setup MQTT monitoring")
            return False
        
        # Wait for test duration
        print(f"\n⏳ Running test for {TEST_DURATION_SECONDS} seconds...")
        time.sleep(TEST_DURATION_SECONDS)
        
        # Stop listening
        for client in clients.values():
            if client:
                client.loop_stop()
        
        return True
        
    except KeyboardInterrupt:
        print("\n\n⏸️  Test interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        return False
    finally:
        # Cleanup
        for client in clients.values():
            if client:
                try:
                    client.loop_stop()
                    client.disconnect()
                except:
                    pass
        
        stop_pipeline("oncloud")
        stop_pipeline("ondevice")


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

def print_report():
    """Print test results"""
    
    print("\n" + "="*80)
    print("  TEST RESULTS")
    print("="*80)
    
    for pipeline in ["oncloud", "ondevice"]:
        results = test_results[pipeline]
        latencies = results["latencies"]
        
        print(f"\n{'─'*80}")
        print(f"  {pipeline.upper()}")
        print(f"{'─'*80}")
        print(f"  MQTT Connected:        {'✅ Yes' if results['mqtt_connected'] else '❌ No'}")
        print(f"  Requests Received:     {results['requests_received']}")
        print(f"  Telemetry Received:    {results['telemetry_received']}")
        print(f"  Policy Updates:        {results['policy_received']}")
        
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)
            print(f"\n  Latency Statistics:")
            print(f"    Average:           {avg_latency:.2f} ms")
            print(f"    Min:               {min_latency:.2f} ms")
            print(f"    Max:               {max_latency:.2f} ms")
            print(f"    Samples:           {len(latencies)}")
        
        if results["errors"]:
            print(f"\n  ⚠️  Errors ({len(results['errors'])}):")
            for error in results["errors"][:5]:  # Show first 5
                print(f"    - {error}")
    
    # Comparison
    print(f"\n{'─'*80}")
    print("  COMPARISON")
    print(f"{'─'*80}")
    
    oncloud_latencies = test_results["oncloud"]["latencies"]
    ondevice_latencies = test_results["ondevice"]["latencies"]
    
    if oncloud_latencies and ondevice_latencies:
        oncloud_avg = sum(oncloud_latencies) / len(oncloud_latencies)
        ondevice_avg = sum(ondevice_latencies) / len(ondevice_latencies)
        
        if ondevice_avg > 0:
            speedup = oncloud_avg / ondevice_avg
            print(f"  On-Cloud Avg Latency:  {oncloud_avg:.2f} ms")
            print(f"  On-Device Avg Latency: {ondevice_avg:.2f} ms")
            print(f"  Speedup:               {speedup:.2f}x")
        
        oncloud_telemetry = test_results["oncloud"]["telemetry_received"]
        ondevice_telemetry = test_results["ondevice"]["telemetry_received"]
        
        print(f"\n  On-Cloud Telemetry:    {oncloud_telemetry} messages")
        print(f"  On-Device Telemetry:   {ondevice_telemetry} messages")
        print(f"  Total:                 {oncloud_telemetry + ondevice_telemetry} messages")
    
    print(f"\n{'─'*80}\n")
    
    # Save results to JSON
    output_file = PROJECT_ROOT / "test_results.json"
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": TEST_DURATION_SECONDS,
            "results": test_results,
            "latency_by_stream": {
                "oncloud": {k: v for k, v in latency_tracker["oncloud"].items()},
                "ondevice": {k: v for k, v in latency_tracker["ondevice"].items()},
            }
        }, f, indent=2)
    
    print(f"✅ Results saved to: {output_file}\n")
    
    # Determine overall pass/fail
    oncloud_ok = test_results["oncloud"]["mqtt_connected"] and test_results["oncloud"]["telemetry_received"] > 0
    ondevice_ok = test_results["ondevice"]["mqtt_connected"] and test_results["ondevice"]["telemetry_received"] > 0
    
    if oncloud_ok and ondevice_ok:
        print("✅ TEST PASSED: Both pipelines running successfully")
        return 0
    else:
        print("❌ TEST FAILED: One or both pipelines not working properly")
        return 1


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    success = run_test()
    exit_code = print_report()
    sys.exit(exit_code)
