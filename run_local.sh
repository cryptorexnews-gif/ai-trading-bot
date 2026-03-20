#!/bin/bash

# Script per avviare Hyperliquid Trading Bot in locale
# Avvia backend API server e frontend dashboard

set -e

echo "🚀 Avvio Hyperliquid Trading Bot in locale..."

# Controlla se .env esiste
if [ ! -f .env ]; then
    echo "⚠️  File .env non trovato!"
    echo "📋 Copia .env.example in .env e modifica le variabili:"
    echo "   cp .env.example .env"
    echo "   nano .env"
    exit 1
fi

# Controlla dipendenze Python
echo "🔍 Controllo dipendenze Python..."
if ! python3 -c "import requests, eth_account, flask" &>/dev/null; then
    echo "📦 Installazione dipendenze Python..."
    pip install -r requirements.txt
fi

# Controlla dipendenze Node.js
echo "🔍 Controllo dipendenze Node.js..."
if [ ! -d "node_modules" ]; then
    echo "📦 Installazione dipendenze Node.js..."
    npm install
fi

# Crea directory logs se non esiste
mkdir -p logs

# Avvia backend API server in background
echo "🌐 Avvio backend API server (porta 5000)..."
python3 api_server.py &
BACKEND_PID=$!

# Attendi che il backend sia pronto
echo "⏳ Attendo che il backend sia pronto..."
sleep 3

# Avvia frontend dashboard
echo "📊 Avvio frontend dashboard (porta 3000)..."
npm run dev &
FRONTEND_PID=$!

# Funzione per cleanup
cleanup() {
    echo "🛑 Fermo tutti i processi..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

# Trap SIGINT e SIGTERM
trap cleanup SIGINT SIGTERM

echo ""
echo "✅ Tutto avviato!"
echo "   📊 Dashboard: http://localhost:3000"
echo "   🌐 API Server: http://localhost:5000"
echo "   📝 Logs: logs/hyperliquid_bot.log"
echo ""
echo "🔍 Per testare la connessione API:"
echo "   curl -H 'X-API-Key: hyperliquid123-super-secure-key-456' http://localhost:5000/api/health"
echo ""
echo "🛑 Premi Ctrl+C per fermare tutto"

# Mantieni lo script in esecuzione
wait