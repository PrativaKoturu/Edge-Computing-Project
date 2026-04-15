#!/usr/bin/env python3
"""
MQTT Message Monitor
Shows all messages flowing through the edge RL system
Useful for debugging and understanding data flow
"""

import paho.mqtt.client as mqtt
import json
from datetime import datetime
import sys

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
NODE_ID = "zone-a"

# Topics to monitor
TOPICS = [
    f"edge/{NODE_ID}/request",
    f"edge/{NODE_ID}/telemetry",
    f"edge/{NODE_ID}/policy",
]

message_count = {topic: 0 for topic in TOPICS}

def on_connect(client, userdata, flags, rc):
    """Connection callback"""
    if rc == 0:
        print("✅ Connected to MQTT broker")
        for topic in TOPICS:
            client.subscribe(topic)
            print(f"   📡 Subscribed to: {topic}")
    else:
        print(f"❌ Connection failed with code {rc}")

def on_message(client, userdata, msg):
    """Message callback"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    message_count[msg.topic] = message_count.get(msg.topic, 0) + 1
    
    try:
        payload = json.loads(msg.payload.decode())
        payload_str = json.dumps(payload, indent=2)
    except json.JSONDecodeError:
        payload_str = msg.payload.decode()
    
    # Color by topic
    colors = {
        f"edge/{NODE_ID}/request": "\033[94m",      # Blue
        f"edge/{NODE_ID}/telemetry": "\033[92m",    # Green
        f"edge/{NODE_ID}/policy": "\033[93m",       # Yellow
    }
    reset = "\033[0m"
    color = colors.get(msg.topic, reset)
    
    print(f"\n{color}[{timestamp}] 📨 {msg.topic}{reset}")
    print(f"   Size: {len(msg.payload)} bytes")
    print(f"   Payload:")
    for line in payload_str.split('\n'):
        print(f"      {line}")
    
    print(f"   Total messages: {message_count[msg.topic]}")

def on_disconnect(client, userdata, rc):
    """Disconnection callback"""
    if rc != 0:
        print(f"❌ Unexpected disconnection: {rc}")

def main():
    print("\n" + "="*70)
    print("🔍 MQTT Message Monitor - Edge RL System")
    print("="*70)
    print(f"\nConnecting to {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Monitoring node: {NODE_ID}")
    print("\nTopics being monitored:")
    for topic in TOPICS:
        print(f"  • {topic}")
    
    print("\nColor coding:")
    print("  🔵 Blue:   Request messages (traffic generator)")
    print("  🟢 Green:  Telemetry messages (edge device)")
    print("  🟡 Yellow: Policy messages (cloud trainer)")
    
    print("\nWaiting for messages...\n")
    
    client = mqtt.Client(client_id="mqtt-monitor")
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("📊 Session Summary")
        print("="*70)
        for topic, count in message_count.items():
            print(f"{topic}: {count} messages")
        print("="*70 + "\n")
        client.disconnect()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
