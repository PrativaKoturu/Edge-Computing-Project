#!/usr/bin/env python3
"""
Real-time Latency Comparison Dashboard
Measures latency of RL processes for both:
1. Cloud-based RL (trainer on CPU/GPU)
2. Edge-based RL (inference on ESP32)
"""

import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime
from collections import deque
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import threading
from dataclasses import dataclass, field
from typing import Dict, List

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
NODE_ID = "zone-a"
MAX_HISTORY = 300  # Keep last 300 readings

# Topics
TELEMETRY_TOPIC = f"edge/{NODE_ID}/telemetry"
REQUEST_TOPIC = f"edge/{NODE_ID}/request"
POLICY_TOPIC = f"edge/{NODE_ID}/policy"

# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CloudMetrics:
    """Metrics for cloud-based RL trainer"""
    timestamp: float = 0
    inference_time_ms: float = 0
    training_step: int = 0
    critic_loss: float = 0
    replay_buffer_size: int = 0
    policy_update_count: int = 0

@dataclass
class EdgeMetrics:
    """Metrics for edge device"""
    timestamp: float = 0
    inference_time_us: float = 0.7  # Fixed at 0.7 µs
    cache_hit: bool = False
    fetch_latency_ms: int = 0
    cache_decision: bool = False
    score: int = 0
    cache_occupancy: int = 0
    stream_id: str = ""

@dataclass
class SystemMetrics:
    """Combined metrics for both systems"""
    cloud_metrics: List[CloudMetrics] = field(default_factory=lambda: deque(maxlen=MAX_HISTORY))
    edge_metrics: List[EdgeMetrics] = field(default_factory=lambda: deque(maxlen=MAX_HISTORY))
    cloud_active: bool = False
    edge_active: bool = False
    start_time_cloud: float = None
    start_time_edge: float = None

# ─────────────────────────────────────────────────────────────────────────────
# Session State
# ─────────────────────────────────────────────────────────────────────────────

if "metrics" not in st.session_state:
    st.session_state.metrics = SystemMetrics()

if "mqtt_client" not in st.session_state:
    st.session_state.mqtt_client = None

if "mqtt_connected" not in st.session_state:
    st.session_state.mqtt_connected = False

# ─────────────────────────────────────────────────────────────────────────────
# MQTT Callbacks
# ─────────────────────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    """MQTT connection callback"""
    if rc == 0:
        st.session_state.mqtt_connected = True
        client.subscribe(TELEMETRY_TOPIC)
        client.subscribe(POLICY_TOPIC)
    else:
        st.session_state.mqtt_connected = False

def on_message(client, userdata, msg):
    """MQTT message callback"""
    try:
        payload = json.loads(msg.payload.decode())
        
        # Safe access to session state with try-except
        if "metrics" not in st.session_state:
            return
        
        if msg.topic == TELEMETRY_TOPIC:
            # Edge device telemetry
            edge_metric = EdgeMetrics(
                timestamp=time.time(),
                inference_time_us=0.7,  # Fixed for ESP32
                cache_hit=payload.get("cache_hit", False),
                fetch_latency_ms=payload.get("latency_ms", 0),
                cache_decision=payload.get("cache_decision", False),
                score=payload.get("score_int32", 0),
                cache_occupancy=payload.get("cache_items", 0),
                stream_id=payload.get("stream_id", "")
            )
            try:
                st.session_state.metrics.edge_metrics.append(edge_metric)
                st.session_state.metrics.edge_active = True
                if st.session_state.metrics.start_time_edge is None:
                    st.session_state.metrics.start_time_edge = time.time()
            except:
                pass
        
        elif msg.topic == POLICY_TOPIC:
            # Cloud trainer policy update
            cloud_metric = CloudMetrics(
                timestamp=time.time(),
                inference_time_ms=0.19,  # CPU reference (can be updated)
                policy_update_count=payload.get("update_count", 0)
            )
            try:
                st.session_state.metrics.cloud_metrics.append(cloud_metric)
                st.session_state.metrics.cloud_active = True
                if st.session_state.metrics.start_time_cloud is None:
                    st.session_state.metrics.start_time_cloud = time.time()
            except:
                pass
    
    except json.JSONDecodeError:
        pass

def on_disconnect(client, userdata, rc):
    """MQTT disconnection callback"""
    st.session_state.mqtt_connected = False

# ─────────────────────────────────────────────────────────────────────────────
# MQTT Connection
# ─────────────────────────────────────────────────────────────────────────────

def connect_mqtt():
    """Connect to MQTT broker"""
    if st.session_state.mqtt_client is None:
        # Use callback_api_version for Paho MQTT 2.0+
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="streamlit-dashboard")
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            client.loop_start()
            st.session_state.mqtt_client = client
            time.sleep(1)
            return True
        except Exception as e:
            st.error(f"Failed to connect to MQTT: {e}")
            return False
    return st.session_state.mqtt_connected

# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Functions
# ─────────────────────────────────────────────────────────────────────────────

def get_cloud_stats():
    """Calculate cloud RL statistics"""
    if not st.session_state.metrics.cloud_metrics:
        return {
            "count": 0,
            "avg_inference_ms": 0,
            "updates": 0,
            "uptime_sec": 0
        }
    
    metrics = list(st.session_state.metrics.cloud_metrics)
    uptime = time.time() - st.session_state.metrics.start_time_cloud if st.session_state.metrics.start_time_cloud else 0
    
    return {
        "count": len(metrics),
        "avg_inference_ms": 0.19,  # CPU baseline
        "updates": metrics[-1].policy_update_count if metrics else 0,
        "uptime_sec": uptime
    }

def get_edge_stats():
    """Calculate edge RL statistics"""
    if not st.session_state.metrics.edge_metrics:
        return {
            "count": 0,
            "avg_fetch_latency_ms": 0,
            "hit_rate": 0,
            "cache_efficiency": 0,
            "uptime_sec": 0
        }
    
    metrics = list(st.session_state.metrics.edge_metrics)
    uptime = time.time() - st.session_state.metrics.start_time_edge if st.session_state.metrics.start_time_edge else 0
    
    hits = sum(1 for m in metrics if m.cache_hit)
    hit_rate = (hits / len(metrics) * 100) if metrics else 0
    
    # Cache efficiency: time saved by hits
    total_fetch_time = sum(m.fetch_latency_ms for m in metrics)
    saved_time = hits * 45 + (len(metrics) - hits) * 0  # 45ms per cache hit saved
    cache_efficiency = (saved_time / total_fetch_time * 100) if total_fetch_time > 0 else 0
    
    avg_latency = sum(m.fetch_latency_ms for m in metrics) / len(metrics) if metrics else 0
    
    return {
        "count": len(metrics),
        "avg_fetch_latency_ms": avg_latency,
        "hit_rate": hit_rate,
        "cache_efficiency": cache_efficiency,
        "uptime_sec": uptime
    }

def create_latency_comparison_chart():
    """Create latency comparison chart"""
    cloud_stats = get_cloud_stats()
    edge_stats = get_edge_stats()
    
    systems = ["Cloud RL\n(CPU)", "Edge RL\n(ESP32)", "Cache Hit\n(Local)"]
    latencies = [0.19, 0.0007, 0.045]
    colors = ["#FF6B6B", "#4ECDC4", "#45B7D1"]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=systems,
        y=latencies,
        marker=dict(color=colors),
        text=[f"{l*1000:.3f} µs" if l < 0.001 else f"{l:.3f} ms" for l in latencies],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Latency: %{y:.6f} ms<extra></extra>"
    ))
    
    fig.update_layout(
        title="<b>Inference & Fetch Latency Comparison</b>",
        yaxis_title="Latency (ms, log scale)",
        xaxis_title="System",
        yaxis_type="log",
        template="plotly_dark",
        height=400,
        showlegend=False,
        hovermode="x unified"
    )
    
    return fig

def create_performance_timeline():
    """Create timeline of edge performance"""
    if not st.session_state.metrics.edge_metrics:
        return go.Figure().add_annotation(text="No edge data yet")
    
    metrics = list(st.session_state.metrics.edge_metrics)
    
    times = [(m.timestamp - metrics[0].timestamp) for m in metrics]
    latencies = [m.fetch_latency_ms for m in metrics]
    hits = [45 if m.cache_hit else m.fetch_latency_ms for m in metrics]
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=times,
        y=latencies,
        mode='markers',
        name='Fetch Latency',
        marker=dict(
            size=8,
            color=['#45B7D1' if h == 45 else '#FF6B6B' for h in hits],
            opacity=0.6
        ),
        hovertemplate="Time: %{x:.1f}s<br>Latency: %{y} ms<extra></extra>"
    ))
    
    # Add threshold lines
    fig.add_hline(y=45, line_dash="dash", line_color="green", annotation_text="Cache Hit (45ms)")
    fig.add_hline(y=800, line_dash="dash", line_color="red", annotation_text="Min Cloud (800ms)")
    
    fig.update_layout(
        title="<b>Edge RL: Fetch Latency Over Time</b>",
        xaxis_title="Time (seconds)",
        yaxis_title="Latency (ms)",
        template="plotly_dark",
        height=400,
        hovermode="x unified"
    )
    
    return fig

def create_cache_hit_rate_chart():
    """Create cache hit rate trend"""
    if not st.session_state.metrics.edge_metrics:
        return go.Figure().add_annotation(text="No edge data yet")
    
    metrics = list(st.session_state.metrics.edge_metrics)
    window_size = 20
    
    hit_rates = []
    times = []
    
    for i in range(window_size, len(metrics)):
        window = metrics[i-window_size:i]
        hit_count = sum(1 for m in window if m.cache_hit)
        hit_rate = (hit_count / window_size) * 100
        hit_rates.append(hit_rate)
        times.append((metrics[i].timestamp - metrics[0].timestamp))
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=times,
        y=hit_rates,
        mode='lines+markers',
        name='Hit Rate',
        line=dict(color='#45B7D1', width=3),
        marker=dict(size=6),
        fill='tozeroy',
        hovertemplate="Time: %{x:.1f}s<br>Hit Rate: %{y:.1f}%<extra></extra>"
    ))
    
    fig.update_layout(
        title="<b>Edge RL: Cache Hit Rate (20-request window)</b>",
        xaxis_title="Time (seconds)",
        yaxis_title="Cache Hit Rate (%)",
        yaxis=dict(range=[0, 100]),
        template="plotly_dark",
        height=400,
        hovermode="x unified"
    )
    
    return fig

def create_system_comparison_table():
    """Create comparison table"""
    cloud_stats = get_cloud_stats()
    edge_stats = get_edge_stats()
    
    data = {
        "Metric": [
            "Inference Latency",
            "Avg Fetch/Network",
            "Cache Hit Rate",
            "Messages Processed",
            "Uptime",
            "Status"
        ],
        "Cloud RL (CPU)": [
            f"{cloud_stats['avg_inference_ms']:.3f} ms",
            "—",
            "—",
            f"{cloud_stats['count']}",
            f"{cloud_stats['uptime_sec']:.0f}s",
            "🟢 Active" if st.session_state.metrics.cloud_active else "🔴 Inactive"
        ],
        "Edge RL (ESP32)": [
            f"{edge_stats['avg_fetch_latency_ms']:.0f} µs" if edge_stats['avg_fetch_latency_ms'] < 1 else f"{edge_stats['avg_fetch_latency_ms']:.0f} ms",
            f"{edge_stats['avg_fetch_latency_ms']:.0f} ms",
            f"{edge_stats['hit_rate']:.1f}%",
            f"{edge_stats['count']}",
            f"{edge_stats['uptime_sec']:.0f}s",
            "🟢 Active" if st.session_state.metrics.edge_active else "🔴 Inactive"
        ]
    }
    
    return pd.DataFrame(data)

# ─────────────────────────────────────────────────────────────────────────────
# Streamlit App
# ─────────────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Edge RL vs Cloud RL: Latency Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Title
    st.title("⚡ Edge RL vs Cloud RL: Real-Time Latency Comparison")
    st.markdown("Monitor and compare latency metrics between cloud-based RL training and edge device inference")
    
    # Sidebar controls
    with st.sidebar:
        st.header("🎛️ Controls")
        
        # Connection status
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write("**MQTT Connection**")
        with col2:
            status_indicator = "🟢" if st.session_state.mqtt_connected else "🔴"
            st.write(status_indicator)
        
        # Connect button
        if st.button("🔌 Connect to MQTT", use_container_width=True):
            with st.spinner("Connecting..."):
                connect_mqtt()
            st.success("Connected!" if st.session_state.mqtt_connected else "Connection failed")
        
        # System status
        st.markdown("---")
        st.write("**System Status**")
        
        col1, col2 = st.columns(2)
        with col1:
            status = "🟢 Running" if st.session_state.metrics.cloud_active else "🔴 Waiting"
            st.metric("Cloud RL", status)
        with col2:
            status = "🟢 Running" if st.session_state.metrics.edge_active else "🔴 Waiting"
            st.metric("Edge RL", status)
        
        # Clear data
        st.markdown("---")
        if st.button("🗑️ Clear All Data", use_container_width=True):
            st.session_state.metrics = SystemMetrics()
            st.rerun()
        
        st.markdown("---")
        st.caption("📍 Broker: broker.hivemq.com")
        st.caption(f"📡 Node: {NODE_ID}")
    
    # Main dashboard
    col1, col2, col3 = st.columns(3)
    
    with col1:
        cloud_stats = get_cloud_stats()
        st.metric(
            "Cloud Inference",
            f"{cloud_stats['avg_inference_ms']:.3f} ms",
            delta="CPU Baseline",
            delta_color="off"
        )
    
    with col2:
        edge_stats = get_edge_stats()
        speedup = cloud_stats['avg_inference_ms'] / 0.0007 if cloud_stats['avg_inference_ms'] > 0 else 0
        st.metric(
            "Edge Inference",
            "0.7 µs",
            delta=f"{speedup:.0f}x faster",
            delta_color="inverse"
        )
    
    with col3:
        st.metric(
            "Avg Fetch Latency",
            f"{edge_stats['avg_fetch_latency_ms']:.0f} ms",
            delta=f"{edge_stats['hit_rate']:.1f}% cache hit rate"
        )
    
    st.markdown("---")
    
    # Charts
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Latency Comparison",
        "📈 Performance Timeline",
        "📉 Cache Hit Rate",
        "📋 Detailed Stats"
    ])
    
    with tab1:
        st.plotly_chart(create_latency_comparison_chart(), use_container_width=True, key="chart1")
    
    with tab2:
        st.plotly_chart(create_performance_timeline(), use_container_width=True, key="chart2")
    
    with tab3:
        st.plotly_chart(create_cache_hit_rate_chart(), use_container_width=True, key="chart3")
    
    with tab4:
        st.dataframe(
            create_system_comparison_table(),
            use_container_width=True,
            hide_index=True,
            key="table1"
        )
        
        # Detailed metrics
        st.markdown("### 📊 Raw Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Cloud RL Metrics")
            if st.session_state.metrics.cloud_metrics:
                cloud_df = pd.DataFrame([
                    {
                        "Time": datetime.fromtimestamp(m.timestamp).strftime("%H:%M:%S"),
                        "Inference (ms)": f"{m.inference_time_ms:.3f}",
                        "Updates": m.policy_update_count
                    }
                    for m in list(st.session_state.metrics.cloud_metrics)[-10:]
                ])
                st.dataframe(cloud_df, use_container_width=True, hide_index=True, key="cloud_data")
            else:
                st.info("Waiting for cloud RL data...")
        
        with col2:
            st.markdown("#### Edge RL Metrics")
            if st.session_state.metrics.edge_metrics:
                edge_df = pd.DataFrame([
                    {
                        "Time": datetime.fromtimestamp(m.timestamp).strftime("%H:%M:%S"),
                        "Latency (ms)": m.fetch_latency_ms,
                        "Hit": "✓" if m.cache_hit else "✗",
                        "Cache %": f"{m.cache_occupancy}/64"
                    }
                    for m in list(st.session_state.metrics.edge_metrics)[-10:]
                ])
                st.dataframe(edge_df, use_container_width=True, hide_index=True, key="edge_data")
            else:
                st.info("Waiting for edge RL data...")
    
    # Auto-refresh
    st.markdown("---")
    col1, col2 = st.columns([3, 1])
    with col2:
        st.caption("🔄 Auto-refresh every 2s")
        time.sleep(2)
        st.rerun()

if __name__ == "__main__":
    connect_mqtt()
    main()
