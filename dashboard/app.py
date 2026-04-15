"""
Dual Pipeline Latency Dashboard
================================
Real-time monitoring of both edge-rl-oncloud and edge-rl-ondevice pipelines.
Displays latency metrics, message flow, and comparative analysis.
"""

import streamlit as st
import paho.mqtt.client as mqtt
import json
from datetime import datetime, timedelta
from collections import defaultdict, deque
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from threading import Lock
import time

# ─────────────────────────────────────────────────────────────────────────────
# Page Configuration
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Dual Pipeline Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────────────────────────────────
# Session State Initialization
# ─────────────────────────────────────────────────────────────────────────────

if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.oncloud_data = {
        "mqtt_connected": False,
        "requests": deque(maxlen=100),
        "telemetry": deque(maxlen=100),
        "latencies": deque(maxlen=100),
        "hit_rate_window": deque(maxlen=20),
        "policies_received": 0,
        "last_update": None,
    }
    st.session_state.ondevice_data = {
        "mqtt_connected": False,
        "requests": deque(maxlen=100),
        "telemetry": deque(maxlen=100),
        "latencies": deque(maxlen=100),
        "hit_rate_window": deque(maxlen=20),
        "policies_received": 0,
        "last_update": None,
    }
    st.session_state.data_lock = Lock()
    st.session_state.clients = {}

# ─────────────────────────────────────────────────────────────────────────────
# MQTT Setup
# ─────────────────────────────────────────────────────────────────────────────

def create_mqtt_callbacks(pipeline):
    """Create MQTT callbacks for a pipeline"""
    
    def on_connect(client, userdata, flags, rc):
        data_key = f"{pipeline}_data"
        if rc == 0:
            with st.session_state.data_lock:
                st.session_state[data_key]["mqtt_connected"] = True
            client.subscribe(f"edge/+/request", qos=0)
            client.subscribe(f"edge/+/telemetry", qos=0)
            client.subscribe(f"edge/+/policy", qos=0)
    
    def on_disconnect(client, userdata, rc):
        data_key = f"{pipeline}_data"
        if rc != 0:
            with st.session_state.data_lock:
                st.session_state[data_key]["mqtt_connected"] = False
    
    def on_message(client, userdata, msg):
        try:
            data_key = f"{pipeline}_data"
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            with st.session_state.data_lock:
                if "request" in topic:
                    st.session_state[data_key]["requests"].append({
                        "timestamp": datetime.now(),
                        "stream_id": payload.get("stream_id", "unknown"),
                        "payload_kb": payload.get("payload_kb", 0),
                    })
                
                elif "telemetry" in topic:
                    latency = payload.get("latency_ms", 0)
                    hit = payload.get("cache_hit", False)
                    
                    st.session_state[data_key]["telemetry"].append({
                        "timestamp": datetime.now(),
                        "stream_id": payload.get("stream_id", "unknown"),
                        "latency_ms": latency,
                        "cache_hit": hit,
                        "cache_items": payload.get("cache_items", 0),
                        "hit_rate": payload.get("hit_rate", 0),
                    })
                    st.session_state[data_key]["latencies"].append(latency)
                    st.session_state[data_key]["hit_rate_window"].append(1 if hit else 0)
                    st.session_state[data_key]["last_update"] = datetime.now()
                
                elif "policy" in topic:
                    st.session_state[data_key]["policies_received"] += 1
        
        except json.JSONDecodeError:
            pass
        except Exception as e:
            pass
    
    def on_subscribe(client, userdata, mid, granted_qos):
        pass
    
    return on_connect, on_disconnect, on_message, on_subscribe


def setup_mqtt_client(pipeline, broker="localhost", port=1883):
    """Setup and connect MQTT client"""
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"dashboard-{pipeline}")
        on_connect, on_disconnect, on_message, on_subscribe = create_mqtt_callbacks(pipeline)
        
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        client.on_subscribe = on_subscribe
        
        # Determine port based on pipeline
        if pipeline == "oncloud":
            port = 11883
        else:
            port = 1883
        
        client.connect(broker, port, keepalive=60)
        client.loop_start()
        
        st.session_state.clients[pipeline] = client
        return True
    except Exception as e:
        st.error(f"Failed to connect to {pipeline} MQTT: {str(e)}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Visualization Functions
# ─────────────────────────────────────────────────────────────────────────────

def plot_latency_comparison():
    """Plot latency comparison between pipelines"""
    oncloud_latencies = list(st.session_state.oncloud_data["latencies"])
    ondevice_latencies = list(st.session_state.ondevice_data["latencies"])
    
    fig = go.Figure()
    
    if oncloud_latencies:
        fig.add_trace(go.Scatter(
            y=oncloud_latencies,
            name="On-Cloud",
            mode='lines+markers',
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=4),
        ))
    
    if ondevice_latencies:
        fig.add_trace(go.Scatter(
            y=ondevice_latencies,
            name="On-Device",
            mode='lines+markers',
            line=dict(color='#ff7f0e', width=2),
            marker=dict(size=4),
        ))
    
    fig.update_layout(
        title="Latency Over Time",
        xaxis_title="Sample #",
        yaxis_title="Latency (ms)",
        hovermode='x unified',
        height=400,
        template="plotly_dark",
    )
    
    return fig


def plot_hit_rate_comparison():
    """Plot cache hit rate comparison"""
    oncloud_hits = list(st.session_state.oncloud_data["hit_rate_window"])
    ondevice_hits = list(st.session_state.ondevice_data["hit_rate_window"])
    
    oncloud_rate = (sum(oncloud_hits) / len(oncloud_hits) * 100) if oncloud_hits else 0
    ondevice_rate = (sum(ondevice_hits) / len(ondevice_hits) * 100) if ondevice_hits else 0
    
    fig = go.Figure(data=[
        go.Bar(name='On-Cloud', x=['Cache Hit Rate'], y=[oncloud_rate], marker_color='#1f77b4'),
        go.Bar(name='On-Device', x=['Cache Hit Rate'], y=[ondevice_rate], marker_color='#ff7f0e'),
    ])
    
    fig.update_layout(
        title="Cache Hit Rate (Last 20 Requests)",
        yaxis_title="Hit Rate (%)",
        hovermode='x unified',
        height=300,
        template="plotly_dark",
        barmode='group',
        yaxis=dict(range=[0, 100]),
    )
    
    return fig


def plot_latency_distribution():
    """Plot latency distribution as histograms"""
    oncloud_latencies = list(st.session_state.oncloud_data["latencies"])
    ondevice_latencies = list(st.session_state.ondevice_data["latencies"])
    
    fig = go.Figure()
    
    if oncloud_latencies:
        fig.add_trace(go.Histogram(
            x=oncloud_latencies,
            name="On-Cloud",
            opacity=0.7,
            marker_color='#1f77b4',
            nbinsx=20,
        ))
    
    if ondevice_latencies:
        fig.add_trace(go.Histogram(
            x=ondevice_latencies,
            name="On-Device",
            opacity=0.7,
            marker_color='#ff7f0e',
            nbinsx=20,
        ))
    
    fig.update_layout(
        title="Latency Distribution",
        xaxis_title="Latency (ms)",
        yaxis_title="Frequency",
        barmode='overlay',
        height=350,
        template="plotly_dark",
    )
    
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Main Dashboard
# ─────────────────────────────────────────────────────────────────────────────

def main():
    st.title("📊 Dual Pipeline Monitoring Dashboard")
    st.markdown("Real-time comparison of **On-Cloud** vs **On-Device** edge RL pipelines")
    
    # Sidebar for connection setup
    with st.sidebar:
        st.header("🔌 Connection Settings")
        
        broker_cloud = st.text_input("On-Cloud MQTT Broker", value="localhost", key="broker_cloud")
        port_cloud = st.number_input("On-Cloud Port", value=11883, key="port_cloud")
        
        broker_device = st.text_input("On-Device MQTT Broker", value="localhost", key="broker_device")
        port_device = st.number_input("On-Device Port", value=1883, key="port_device")
        
        if st.button("🔄 Connect", use_container_width=True):
            st.session_state.clients.clear()
            setup_mqtt_client("oncloud", broker_cloud, port_cloud)
            setup_mqtt_client("ondevice", broker_device, port_device)
            st.success("Connection attempts made!")
        
        st.divider()
        
        # Connection status
        col1, col2 = st.columns(2)
        
        with col1:
            status_cloud = "🟢 Connected" if st.session_state.oncloud_data["mqtt_connected"] else "🔴 Disconnected"
            st.metric("On-Cloud", status_cloud)
        
        with col2:
            status_device = "🟢 Connected" if st.session_state.ondevice_data["mqtt_connected"] else "🔴 Disconnected"
            st.metric("On-Device", status_device)
        
        st.divider()
        
        # Auto-refresh
        refresh_interval = st.slider("Refresh Interval (seconds)", 1, 10, 2, key="refresh")
        if "last_refresh" not in st.session_state:
            st.session_state.last_refresh = time.time()
    
    # Auto-refresh placeholder
    placeholder = st.empty()
    
    # Main metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        oncloud_latencies = list(st.session_state.oncloud_data["latencies"])
        oncloud_avg = (sum(oncloud_latencies) / len(oncloud_latencies)) if oncloud_latencies else 0
        st.metric("On-Cloud Avg Latency", f"{oncloud_avg:.2f} ms", delta=None)
    
    with col2:
        ondevice_latencies = list(st.session_state.ondevice_data["latencies"])
        ondevice_avg = (sum(ondevice_latencies) / len(ondevice_latencies)) if ondevice_latencies else 0
        st.metric("On-Device Avg Latency", f"{ondevice_avg:.2f} ms", delta=None)
    
    with col3:
        oncloud_telemetry = len(st.session_state.oncloud_data["telemetry"])
        st.metric("On-Cloud Telemetry", oncloud_telemetry)
    
    with col4:
        ondevice_telemetry = len(st.session_state.ondevice_data["telemetry"])
        st.metric("On-Device Telemetry", ondevice_telemetry)
    
    st.divider()
    
    # Latency comparison chart
    st.subheader("📈 Latency Over Time")
    try:
        st.plotly_chart(plot_latency_comparison(), use_container_width=True)
    except:
        st.info("Waiting for latency data...")
    
    # Two column layout
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🎯 Hit Rate Comparison")
        try:
            st.plotly_chart(plot_hit_rate_comparison(), use_container_width=True)
        except:
            st.info("Waiting for telemetry data...")
    
    with col2:
        st.subheader("📊 Latency Distribution")
        try:
            st.plotly_chart(plot_latency_distribution(), use_container_width=True)
        except:
            st.info("Waiting for latency data...")
    
    st.divider()
    
    # Detailed metrics tables
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("On-Cloud Pipeline")
        oncloud_data = st.session_state.oncloud_data
        oncloud_latencies = list(oncloud_data["latencies"])
        
        metrics = {
            "Requests": len(oncloud_data["requests"]),
            "Telemetry Messages": len(oncloud_data["telemetry"]),
            "Policies Received": oncloud_data["policies_received"],
            "Min Latency (ms)": f"{min(oncloud_latencies):.2f}" if oncloud_latencies else "N/A",
            "Max Latency (ms)": f"{max(oncloud_latencies):.2f}" if oncloud_latencies else "N/A",
            "Avg Latency (ms)": f"{(sum(oncloud_latencies) / len(oncloud_latencies)):.2f}" if oncloud_latencies else "N/A",
        }
        
        df_oncloud = pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"])
        st.dataframe(df_oncloud, use_container_width=True, hide_index=True)
    
    with col2:
        st.subheader("On-Device Pipeline")
        ondevice_data = st.session_state.ondevice_data
        ondevice_latencies = list(ondevice_data["latencies"])
        
        metrics = {
            "Requests": len(ondevice_data["requests"]),
            "Telemetry Messages": len(ondevice_data["telemetry"]),
            "Policies Received": ondevice_data["policies_received"],
            "Min Latency (ms)": f"{min(ondevice_latencies):.2f}" if ondevice_latencies else "N/A",
            "Max Latency (ms)": f"{max(ondevice_latencies):.2f}" if ondevice_latencies else "N/A",
            "Avg Latency (ms)": f"{(sum(ondevice_latencies) / len(ondevice_latencies)):.2f}" if ondevice_latencies else "N/A",
        }
        
        df_ondevice = pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"])
        st.dataframe(df_ondevice, use_container_width=True, hide_index=True)
    
    st.divider()
    
    # Recent telemetry data
    st.subheader("📥 Recent Telemetry Data")
    
    tab_oncloud, tab_ondevice = st.tabs(["On-Cloud", "On-Device"])
    
    with tab_oncloud:
        oncloud_telemetry = list(st.session_state.oncloud_data["telemetry"])
        if oncloud_telemetry:
            df = pd.DataFrame(oncloud_telemetry[-10:]).iloc[::-1]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No telemetry data yet")
    
    with tab_ondevice:
        ondevice_telemetry = list(st.session_state.ondevice_data["telemetry"])
        if ondevice_telemetry:
            df = pd.DataFrame(ondevice_telemetry[-10:]).iloc[::-1]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No telemetry data yet")
    
    # Auto-refresh
    import time
    time.sleep(st.session_state.refresh_interval)
    st.rerun()


if __name__ == "__main__":
    main()
