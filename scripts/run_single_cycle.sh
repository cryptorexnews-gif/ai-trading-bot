#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Esegue un singolo ciclo di trading (test rapido)
# ═══════════════════════════════════════════════════════════════

set -e

echo "🤖 Hyperliquid Trading Bot — Singolo Ciclo di Test"
echo "=================================================="
echo ""

# Verifica che .env esista
if [ ! -f .env ]; then
    echo "❌ File .env non trovato!"
    echo "   Copia .env.example come .env e compila i valori:"
    echo "   cp .env.example .env"
    exit 1
fi

# Crea directory necessarie
mkdir -p state logs

# Esegui test connessione prima
echo "📡 Verifica connessione..."
python scripts/test_connection.py
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Test connessione fallito. Correggi gli errori prima di procedere."
    exit 1
fi

echo ""
echo "🚀 Avvio singolo ciclo di trading..."
echo ""

python hyperliquid_bot_executable_orders.py --single-cycle

echo ""
echo "✅ Ciclo completato. Controlla i log in logs/hyperliquid_bot.log"