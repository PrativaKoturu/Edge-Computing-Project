"""
On-Device RL Monitor
Subscribes to edge-rl-node telemetry and prints live learning progress.
Run while Wokwi + Docker are both running.

  python3 monitor.py
"""
import json, time, threading
import paho.mqtt.client as mqtt

BROKER = "broker.hivemq.com"
TOPIC  = "edge/edge-rl-node/telemetry"

stats = {
    "steps": 0, "hits": 0, "last_reward": 0.0,
    "last_td": 0.0, "epsilon": 0.5, "hit_rate": 0.0,
}
lock = threading.Lock()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[monitor] Connected to {BROKER}")
        client.subscribe(TOPIC)
        print(f"[monitor] Subscribed: {TOPIC}\n")
    else:
        print(f"[monitor] Connection failed rc={rc}")

def on_message(client, userdata, msg):
    try:
        d = json.loads(msg.payload)
        with lock:
            stats["steps"]       = d.get("total_steps", 0)
            stats["hit_rate"]    = d.get("hit_rate", 0.0) * 100
            stats["last_reward"] = d.get("reward", 0.0)
            stats["last_td"]     = d.get("td_error", 0.0)
            stats["epsilon"]     = d.get("epsilon", 0.5)

        hit    = "HIT  " if d.get("cache_hit") else "MISS "
        action = "CACHE" if d.get("cache_decision") else "SKIP "
        td     = d.get("td_error", 0.0)
        r      = d.get("reward", 0.0)
        eps    = d.get("epsilon", 0.5)
        hr     = d.get("hit_rate", 0.0) * 100
        stream = d.get("stream_id", "")[:35]

        # colour: green for positive td, red for negative
        td_str = f"\033[92m{td:+.4f}\033[0m" if td > 0 else f"\033[91m{td:+.4f}\033[0m"

        print(
            f"  step={stats['steps']:4d}  {hit}  action={action}  "
            f"reward={r:+.3f}  td={td_str}  eps={eps:.3f}  "
            f"hit_rate={hr:5.1f}%   {stream}"
        )
    except Exception as e:
        print(f"[monitor] parse error: {e}")

def main():
    print("=" * 80)
    print(" On-Device Q-Learning Monitor")
    print(f" Broker : {BROKER}")
    print(f" Topic  : {TOPIC}")
    print("=" * 80)
    print()
    print("  What to watch:")
    print("   td_error  → should fluctuate but trend toward 0 (model improving)")
    print("   hit_rate  → should climb from 0% toward 10–15% over ~200 steps")
    print("   epsilon   → decays 0.50 → 0.05 (less random, more policy-driven)")
    print("   action    → early: mostly random CACHE/SKIP, later: consistent policy")
    print()
    print("  Ctrl+C to stop\n")

    client = mqtt.Client(client_id=f"monitor-{int(time.time())}")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, 1883, keepalive=60)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[monitor] Stopped.")
        with lock:
            print(f"\nFinal stats after {stats['steps']} steps:")
            print(f"  Hit rate : {stats['hit_rate']:.1f}%")
            print(f"  Epsilon  : {stats['epsilon']:.3f}")
        client.disconnect()

if __name__ == "__main__":
    main()
