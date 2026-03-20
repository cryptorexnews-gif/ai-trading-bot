#!/bin/bash

# Script per pulire il progetto Hyperliquid Trading Bot

echo "🤖 Avvio pulizia progetto Hyperliquid Trading Bot"
echo "=================================================="

# Verifica Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 non trovato. Installa Python 3.10+"
    exit 1
fi

# Esegui lo script di pulizia
python3 cleanup_script.py

echo ""
echo "✅ Pulizia completata!"
echo ""
echo "📋 Prossimi passi:"
echo "1. Configura il file .env:"
echo "   cp .env.example .env"
echo "   nano .env"
echo ""
echo "2. Testa il bot:"
echo "   python hyperliquid_bot_executable_orders.py --single-cycle"
echo ""
echo "3. Avvia tutto:"
echo "   # Terminale 1: python hyperliquid_bot_executable_orders.py"
echo "   # Terminale 2: python api_server.py"
echo "   # Terminale 3: cd frontend && npm run dev"