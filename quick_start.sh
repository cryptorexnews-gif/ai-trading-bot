#!/bin/bash

# Script di avvio rapido per Hyperliquid Trading Bot
# Esegue tutti i passi necessari per iniziare

set -e

echo "🚀 AVVIO RAPIDO HYPERLIQUID TRADING BOT"
echo "========================================"

# 1. Verifica prerequisiti
echo "1. Verifica prerequisiti..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 non installato"
    exit 1
fi

if ! command -v npm &> /dev/null; then
    echo "❌ Node.js/npm non installato"
    exit 1
fi

# 2. Setup ambiente
echo "2. Setup ambiente..."
if [ ! -f .env ]; then
    echo "📋 Creazione file .env da template..."
    cp .env.example .env
    echo "⚠️  MODIFICA il file .env con le tue chiavi!"
    echo "   Variabili MINIME da configurare:"
    echo "   - HYPERLIQUID_WALLET_ADDRESS"
    echo "   - HYPERLIQUID_PRIVATE_KEY"
    echo "   - OPENROUTER_API_KEY"
    echo "   - DASHBOARD_API_KEY"
    echo "   - VITE_DASHBOARD_API_KEY"
    echo ""
    echo "📝 Apri .env con il tuo editor e modifica le variabili."
    echo "   Poi esegui di nuovo questo script."
    exit 1
fi

# 3. Installa dipendenze
echo "3. Installazione dipendenze..."
echo "   Python..."
pip install -r requirements.txt > /dev/null 2>&1 || {
    echo "❌ Errore installazione dipendenze Python"
    exit 1
}

echo "   Node.js..."
npm install > /dev/null 2>&1 || {
    echo "❌ Errore installazione dipendenze Node.js"
    exit 1
}

# 4. Crea directory logs
echo "4. Creazione directory logs..."
mkdir -p logs

# 5. Test configurazione
echo "5. Test configurazione..."
python3 test_local.py
if [ $? -ne 0 ]; then
    echo "❌ Test fallito. Controlla i messaggi sopra."
    exit 1
fi

echo ""
echo "✅ TUTTO PRONTO!"
echo "================"
echo ""
echo "Per avviare tutto:"
echo "  ./run_local.sh"
echo ""
echo "Oppure manualmente:"
echo "  Terminale 1: python api_server.py"
echo "  Terminale 2: npm run dev"
echo ""
echo "📊 Dashboard: http://localhost:3000"
echo "🌐 API Server: http://localhost:5000"
echo ""
echo "Per testare un ciclo di trading:"
echo "  python hyperliquid_bot_executable_orders.py --single-cycle"