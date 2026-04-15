#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# Dual Pipeline Startup Script
# ═══════════════════════════════════════════════════════════════════════════════
# 
# This script starts both edge-rl-oncloud and edge-rl-ondevice pipelines
# and optionally launches the Streamlit dashboard.
#
# Usage:
#   ./start_dual_pipeline.sh                    # Start both pipelines
#   ./start_dual_pipeline.sh --with-dashboard   # Include dashboard
#   ./start_dual_pipeline.sh --test             # Run test suite
#
# ═══════════════════════════════════════════════════════════════════════════════

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ONCLOUD_DIR="$PROJECT_ROOT/edge-rl-oncloud"
ONDEVICE_DIR="$PROJECT_ROOT/edge-rl-ondevice"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

print_header() {
    echo -e "\n${BLUE}╔════════════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  $1"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════════════════════════╝${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅${NC}  $1"
}

print_error() {
    echo -e "${RED}❌${NC}  $1"
}

print_info() {
    echo -e "${YELLOW}ℹ️${NC}  $1"
}

# ─────────────────────────────────────────────────────────────────────────────
# Prerequisite Checks
# ─────────────────────────────────────────────────────────────────────────────

check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker not found. Please install Docker Desktop."
        exit 1
    fi
    print_success "Docker is installed"
    
    # Check Docker daemon
    if ! docker ps &> /dev/null; then
        print_error "Docker daemon not running. Please start Docker Desktop."
        exit 1
    fi
    print_success "Docker daemon is running"
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 not found. Please install Python 3.11+"
        exit 1
    fi
    print_success "Python3 is installed"
    
    # Check data file
    if [ ! -f "$PROJECT_ROOT/data/ai4i2020.csv" ]; then
        print_error "Dataset not found. Downloading..."
        cd "$PROJECT_ROOT"
        python3 download_dataset.py
    fi
    print_success "Dataset is available"
}

# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Start/Stop
# ─────────────────────────────────────────────────────────────────────────────

start_pipeline() {
    local pipeline=$1
    local dir=$2
    
    print_info "Starting $pipeline pipeline..."
    
    cd "$dir"
    docker compose up -d
    
    # Wait for services to be ready
    sleep 5
    
    print_success "$pipeline pipeline started"
}

stop_pipeline() {
    local pipeline=$1
    local dir=$2
    
    print_info "Stopping $pipeline pipeline..."
    
    cd "$dir"
    docker compose down
    
    print_success "$pipeline pipeline stopped"
}

show_status() {
    print_header "Pipeline Status"
    
    echo -e "${BLUE}On-Cloud Pipeline (port 11883):${NC}"
    cd "$ONCLOUD_DIR"
    docker compose ps
    
    echo ""
    echo -e "${BLUE}On-Device Pipeline (port 1883):${NC}"
    cd "$ONDEVICE_DIR"
    docker compose ps
}

show_logs() {
    local pipeline=$1
    local dir=$2
    
    echo -e "\n${BLUE}Logs for $pipeline:${NC}\n"
    cd "$dir"
    docker compose logs -f --tail=50
}

# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

start_dashboard() {
    print_header "Starting Streamlit Dashboard"
    
    print_info "Installing dashboard dependencies..."
    pip install -q -r "$PROJECT_ROOT/dashboard/requirements.txt"
    print_success "Dependencies installed"
    
    print_info "Launching dashboard at http://localhost:8501..."
    cd "$PROJECT_ROOT/dashboard"
    streamlit run app.py
}

# ─────────────────────────────────────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────────────────────────────────────

run_test() {
    print_header "Running Dual Pipeline Test Suite"
    
    print_info "Installing test dependencies..."
    pip install -q paho-mqtt
    print_success "Dependencies installed"
    
    print_info "Starting test..."
    cd "$PROJECT_ROOT"
    python3 test_dual_pipeline.py
}

# ─────────────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────────────

cleanup() {
    echo -e "\n\n${YELLOW}Shutting down...${NC}"
    stop_pipeline "on-cloud" "$ONCLOUD_DIR"
    stop_pipeline "on-device" "$ONDEVICE_DIR"
    print_success "All pipelines stopped"
    exit 0
}

# ─────────────────────────────────────────────────────────────────────────────
# Main Menu
# ─────────────────────────────────────────────────────────────────────────────

main() {
    print_header "Edge Computing Dual Pipeline Manager"
    
    # Parse arguments
    case "${1:-}" in
        --with-dashboard)
            check_prerequisites
            start_pipeline "on-cloud" "$ONCLOUD_DIR"
            start_pipeline "on-device" "$ONDEVICE_DIR"
            show_status
            trap cleanup SIGINT
            start_dashboard
            ;;
        --test)
            check_prerequisites
            run_test
            ;;
        --logs-oncloud)
            show_logs "on-cloud" "$ONCLOUD_DIR"
            ;;
        --logs-ondevice)
            show_logs "on-device" "$ONDEVICE_DIR"
            ;;
        --status)
            show_status
            ;;
        --stop)
            stop_pipeline "on-cloud" "$ONCLOUD_DIR"
            stop_pipeline "on-device" "$ONDEVICE_DIR"
            ;;
        *)
            check_prerequisites
            print_header "Starting Both Pipelines"
            start_pipeline "on-cloud" "$ONCLOUD_DIR"
            start_pipeline "on-device" "$ONDEVICE_DIR"
            show_status
            
            trap cleanup SIGINT
            
            echo -e "\n${GREEN}Both pipelines are running!${NC}"
            echo -e "\n${BLUE}Available commands:${NC}"
            echo -e "  ./start_dual_pipeline.sh --status         # Show status"
            echo -e "  ./start_dual_pipeline.sh --logs-oncloud   # View on-cloud logs"
            echo -e "  ./start_dual_pipeline.sh --logs-ondevice  # View on-device logs"
            echo -e "  ./start_dual_pipeline.sh --with-dashboard # Start with dashboard"
            echo -e "  ./start_dual_pipeline.sh --test           # Run test suite"
            echo -e "  ./start_dual_pipeline.sh --stop           # Stop all pipelines"
            echo -e "\n${YELLOW}Press Ctrl+C to stop${NC}"
            
            while true; do
                sleep 100
            done
            ;;
    esac
}

# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

main "$@"
