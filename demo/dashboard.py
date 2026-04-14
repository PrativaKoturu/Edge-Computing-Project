from __future__ import annotations

import json
import os
import time
from collections import deque, defaultdict
from dataclasses import dataclass

import paho.mqtt.client as mqtt
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None else v


@dataclass
class NodeStats:
    total: int = 0
    hits: int = 0
    latency_sum: float = 0.0
    cache_items: int = 0


class DashboardState:
    def __init__(self) -> None:
        self.message_flow: deque[tuple[str, str]] = deque(maxlen=10)
        self.node_stats: dict[str, NodeStats] = defaultdict(NodeStats)
        self.critic_updates: int = 0
        self.policy_publishes: int = 0
        self.replay_size: int = 0
        self.critic_loss_avg10: float = 0.0
        self.actor_loss_avg10: float = 0.0
        self.float_weights: list[float] = []
        self.int8_weights: list[int] = []
        self.anomalies: deque[str] = deque(maxlen=5)

    def push_flow(self, topic: str, summary: str, kind: str) -> None:
        color = {"request": "blue", "telemetry": "yellow", "policy": "green"}.get(kind, "white")
        self.message_flow.append((topic, str(Text(summary, style=color))))


def _render_message_flow(st: DashboardState) -> Panel:
    t = Table.grid(expand=True)
    t.add_column(justify="left")
    t.add_column(justify="left")
    for topic, summary in list(st.message_flow)[-10:]:
        t.add_row(topic, summary)
    return Panel(t, title="MQTT Message Flow (last 10)")


def _render_per_node(st: DashboardState) -> Panel:
    t = Table(expand=True)
    t.add_column("Node")
    t.add_column("Hit rate %", justify="right")
    t.add_column("Avg latency ms", justify="right")
    t.add_column("Cache items", justify="right")
    t.add_column("Total req", justify="right")
    for node_id, ns in sorted(st.node_stats.items()):
        hit_rate = (100.0 * ns.hits / ns.total) if ns.total else 0.0
        avg_lat = (ns.latency_sum / ns.total) if ns.total else 0.0
        t.add_row(node_id, f"{hit_rate:.1f}", f"{avg_lat:.1f}", str(ns.cache_items), str(ns.total))
    return Panel(t, title="Per-Node Cache Stats")


def _render_training(st: DashboardState) -> Panel:
    t = Table.grid(expand=True)
    t.add_column()
    t.add_column(justify="right")
    t.add_row("Replay buffer size", str(st.replay_size))
    t.add_row("Critic updates", str(st.critic_updates))
    t.add_row("Critic loss (avg10)", f"{st.critic_loss_avg10:.4f}")
    t.add_row("Actor loss (avg10)", f"{st.actor_loss_avg10:.4f}")
    t.add_row("Policy publishes", str(st.policy_publishes))
    return Panel(t, title="RL Training Stats")


def _render_weights(st: DashboardState) -> Panel:
    t = Table(expand=True)
    t.add_column("i")
    t.add_column("float32", justify="right")
    t.add_column("int8", justify="right")
    for i in range(8):
        fw = st.float_weights[i] if i < len(st.float_weights) else 0.0
        iw = st.int8_weights[i] if i < len(st.int8_weights) else 0
        t.add_row(str(i), f"{fw:+.4f}", str(iw))
    return Panel(t, title="Policy Weights (float vs int8)")


def _render_anomalies(st: DashboardState) -> Panel:
    t = Table.grid(expand=True)
    t.add_column()
    for s in st.anomalies:
        t.add_row(s)
    return Panel(t, title="Anomaly Events (last 5)")


def _layout(st: DashboardState) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="top", ratio=2),
        Layout(name="mid", ratio=2),
        Layout(name="bot", ratio=1),
    )
    layout["top"].split_row(
        Layout(_render_message_flow(st), name="flow", ratio=2),
        Layout(_render_per_node(st), name="nodes", ratio=3),
    )
    layout["mid"].split_row(
        Layout(_render_training(st), name="train", ratio=2),
        Layout(_render_weights(st), name="weights", ratio=2),
    )
    layout["bot"].update(_render_anomalies(st))
    return layout


def main() -> None:
    console = Console()
    host = _env("MQTT_HOST", "broker.hivemq.com")
    port = int(_env("MQTT_PORT", "1883"))

    st = DashboardState()

    def on_connect(client: mqtt.Client, userdata, flags, rc):
        client.subscribe("edge/+/request", qos=0)
        client.subscribe("edge/+/telemetry", qos=0)
        client.subscribe("edge/+/policy", qos=0)
        client.subscribe("trainer/stats", qos=0)

    def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace")

        if "/request" in topic:
            d = json.loads(payload)
            summ = f"{d.get('node_id')} {d.get('stream_id')} kb={d.get('payload_kb')} anom={d.get('anomaly')}"
            st.push_flow(topic, summ, "request")
            if d.get("anomaly"):
                st.anomalies.appendleft(f"{d.get('node_id')} {d.get('stream_id')} kb={d.get('payload_kb')}")
            return

        if "/telemetry" in topic:
            d = json.loads(payload)
            node = str(d.get("node_id"))
            ns = st.node_stats[node]
            ns.total += 1
            if d.get("cache_hit"):
                ns.hits += 1
            ns.latency_sum += float(d.get("latency_ms", 0))
            ns.cache_items = int(d.get("cache_items", 0))
            summ = f"{node} hit={d.get('cache_hit')} lat={d.get('latency_ms')}ms score={d.get('score_int32')}"
            st.push_flow(topic, summ, "telemetry")
            return

        if "/policy" in topic:
            d = json.loads(payload)
            st.float_weights = [float(x) for x in d.get("float_weights", [])]
            st.int8_weights = [int(x) for x in d.get("int8_weights", [])]
            summ = f"{d.get('node_id')} policy update int8[0]={st.int8_weights[0] if st.int8_weights else None}"
            st.push_flow(topic, summ, "policy")
            st.policy_publishes += 1
            return

        if topic == "trainer/stats":
            d = json.loads(payload)
            st.replay_size = int(d.get("replay_size", st.replay_size))
            st.critic_updates = int(d.get("critic_updates", st.critic_updates))
            st.critic_loss_avg10 = float(d.get("critic_loss_avg10", st.critic_loss_avg10))
            st.actor_loss_avg10 = float(d.get("actor_loss_avg10", st.actor_loss_avg10))
            return

    client = mqtt.Client(client_id=f"dashboard-{os.getpid()}", clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, keepalive=30)
    client.loop_start()

    console.print(f"Dashboard connected to MQTT {host}:{port}")
    with Live(_layout(st), refresh_per_second=1, screen=True):
        while True:
            time.sleep(1)


if __name__ == "__main__":
    main()

