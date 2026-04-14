#!/bin/bash
# Quick Wokwi Setup Script
# Installs dependencies and helps you get started

set -e

echo "=================================="
echo "Wokwi Edge Computing Setup"
echo "=================================="
echo ""

# Check Node.js
echo "Checking Node.js..."
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Installing..."
    # macOS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install node
    # Linux
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
        sudo apt-get install -y nodejs
    fi
fi
echo "✓ Node.js: $(node --version)"
echo ""

# Check npm
echo "Checking npm..."
if ! command -v npm &> /dev/null; then
    echo "❌ npm not found"
    exit 1
fi
echo "✓ npm: $(npm --version)"
echo ""

# Install wokwi-cli
echo "Installing wokwi-cli..."
if ! command -v wokwi-cli &> /dev/null; then
    npm install -g wokwi-cli
    echo "✓ wokwi-cli installed globally"
else
    echo "✓ wokwi-cli already installed: $(wokwi-cli --version)"
fi
echo ""

# Check PlatformIO
echo "Checking PlatformIO..."
if ! command -v pio &> /dev/null; then
    echo "❌ PlatformIO not found. Installing..."
    pip3 install platformio
fi
echo "✓ PlatformIO: $(pio --version)"
echo ""

# Check Docker
echo "Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "⚠ Docker not found. You'll need it to run the control plane."
    echo "  Install from: https://www.docker.com/products/docker-desktop"
else
    echo "✓ Docker: $(docker --version)"
    # Check docker compose
    if docker compose version &> /dev/null; then
        echo "✓ Docker Compose: $(docker compose version | head -1)"
    else
        echo "⚠ Docker Compose not available. May need to install: pip install docker-compose"
    fi
fi
echo ""

# Python requirements
echo "Checking Python dependencies..."
python3 -m pip install -q paho-mqtt rich 2>/dev/null
echo "✓ Python dependencies installed"
echo ""

# Firmware check
echo "Checking firmware..."
if [ -f "firmware/platformio.ini" ]; then
    echo "✓ Found firmware/platformio.ini"
    cd firmware
    echo "  Building zone-a firmware..."
    pio run -e zone-a -q
    echo "  Building zone-b firmware..."
    pio run -e zone-b -q
    echo "✓ Firmware built successfully"
    cd ..
else
    echo "❌ firmware/platformio.ini not found"
    exit 1
fi
echo ""

echo "=================================="
echo "✓ Setup Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Start the control plane (Terminal 1):"
echo "   docker compose up --build"
echo ""
echo "2. Start Zone A simulator (Terminal 2):"
echo "   cd firmware"
echo "   wokwi-cli --build-type pio --project . zone-a --port 9001"
echo ""
echo "3. Start Zone B simulator (Terminal 3):"
echo "   cd firmware"
echo "   wokwi-cli --build-type pio --project . zone-b --port 9002"
echo ""
echo "4. Start the comparison dashboard (Terminal 4):"
echo "   python3 demo/wokwi_comparison_dashboard.py"
echo ""
echo "For detailed instructions, see: WOKWI_SETUP.md"
echo ""
