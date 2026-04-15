#!/bin/bash

# Latency Dashboard Setup Script
# Run this once to install dependencies and set up the dashboard

echo "🚀 Setting up Latency Comparison Dashboard..."
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

echo "📦 Installing Python dependencies..."
pip3 install -r demo/requirements_dashboard.txt

if [ $? -eq 0 ]; then
    echo "✅ Dependencies installed successfully!"
    echo ""
    echo "🎯 To run the dashboard:"
    echo ""
    echo "   streamlit run demo/latency_dashboard.py"
    echo ""
    echo "📊 The dashboard will:"
    echo "   • Connect to broker.hivemq.com via MQTT"
    echo "   • Listen for cloud RL telemetry on: edge/zone-a/policy"
    echo "   • Listen for edge device telemetry on: edge/zone-a/telemetry"
    echo "   • Show real-time latency comparison charts"
    echo "   • Track cache hit rates and performance metrics"
    echo ""
    echo "🔗 Make sure both systems are running:"
    echo "   1. Cloud RL: docker compose up --build"
    echo "   2. Edge RL: Wokwi ESP32 with firmware/src/main.cpp"
    echo ""
else
    echo "❌ Installation failed. Please check your internet connection."
    exit 1
fi
