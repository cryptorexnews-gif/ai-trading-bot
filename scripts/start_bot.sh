#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Avvia il bot di trading completo con dashboard
# ═══════════════════════════════════════════════════════════════

set -e

echo "🤖 Hyperliquid Trading Bot — Avvio Completo"
echo "============================================"
echo ""

# Verifica che .env esista
if [ ! -f .env ]; then
    echo "❌ File .env non trovato!"
    echo "   cp .env.example .env"
    exit 1
fi

# Crea directory
mkdir -p state logs

# Mostra modalità
MODE=$(grep -E "^EXECUTION_MODE=" .env | cut -d= -f2 | tr -d ' "'"'"'')
MAINNET=$(grep -E "^ENABLE_MAINNET_TRADING=" .env | cut -d= -f2 | tr -d ' "'"'"'')

echo "📋 Modalità: ${MODE:-paper}"
echo "📋 Mainnet: ${MAINNET:-false}"
echo ""

if [ "$MODE" = "live" ] && [ "$MAINNET" = "true" ]; then
    echo "⚡⚡⚡ ATTENZIONE: TRADING REALE ABILITATO ⚡⚡⚡"
    echo "Gli ordini verranno eseguiti con soldi veri!"
    echo ""
    read -p "Sei sicuro di voler procedere? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Annullato."
        exit 0
    fi
fi

echo "🚀 Avvio bot di trading..."
echo "   Per fermare: Ctrl+C"
echo ""

python hyperliquid_bot_executable_orders.py