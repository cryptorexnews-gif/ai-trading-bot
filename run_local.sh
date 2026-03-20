#!/bin/bash

# ============================================================================
# Hyperliquid Trading Bot - Local Development Script
# ============================================================================
# This script starts all components needed for local development
# ============================================================================

set -e  # Exit on error

echo "🤖 HYPERLIQUID TRADING BOT - LOCAL DEVELOPMENT"
echo "================================================"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "   Copy .env.example to .env and configure your settings:"
    echo "   cp .env.example .env"
    echo "   nano .env  # Edit with your values"
    exit 1
fi

# Check Python dependencies
echo "🔍 Checking Python dependencies..."
if ! python3 -c "import requests; import eth_account; import flask; import msgpack; from Crypto.Hash import keccak" 2>/dev/null; then
    echo "📦 Installing Python dependencies..."
    pip install -r requirements.txt
fi

# Check Node.js dependencies
echo "🔍 Checking Node.js dependencies..."
if [ ! -d "node_modules" ]; then
    echo "📦 Installing Node.js dependencies..."
    npm install --force
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p logs state

# Start components in background
echo "🚀 Starting components..."

# 1. API Server
echo "🌐 Starting API Server (port 5000)..."
python3 api_server.py &
API_PID=$!
echo "   API Server PID: $API_PID"

# Wait for API server to start
echo "⏳ Waiting for API server to start..."
sleep 3

# Check if API server is running
if ! curl -s http://localhost:5000/api/health > /dev/null; then
    echo "❌ API Server failed to start"
    kill $API_PID 2>/dev/null || true
    exit 1
fi

# 2. Frontend Dashboard
echo "📊 Starting Frontend Dashboard (port 3000)..."
cd frontend
npm run dev &
FRONTEND_PID=$!
echo "   Frontend PID: $FRONTEND_PID"
cd ..

# 3. Bot (optional - comment out if you don't want it running automatically)
# echo "🤖 Starting Trading Bot..."
# python3 hyperliquid_bot_executable_orders.py &
# BOT_PID=$!
# echo "   Bot PID: $BOT_PID"

echo ""
echo "================================================"
echo "🎉 ALL SYSTEMS GO!"
echo "================================================"
echo ""
echo "🔗 URLs:"
echo "   📊 Dashboard: http://localhost:3000"
echo "   🌐 API Server: http://localhost:5000"
echo "   📈 Health Check: http://localhost:5000/api/health"
echo ""
echo "📋 To start the trading bot manually:"
echo "   python hyperliquid_bot_executable_orders.py --single-cycle"
echo ""
echo "🛑 Press Ctrl+C to stop all services"
echo ""

# Trap Ctrl+C to clean up
trap cleanup INT

cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    
    # Kill all background processes
    kill $API_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    # kill $BOT_PID 2>/dev/null || true
    
    echo "✅ Services stopped"
    exit 0
}

# Keep script running
wait