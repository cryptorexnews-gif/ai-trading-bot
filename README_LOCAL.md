# 🚀 Test Locale Hyperliquid Trading Bot

Questa guida ti aiuta a configurare e testare il bot in locale.

## 📋 Prerequisiti

1. **Python 3.10+** installato
2. **Node.js 18+** installato
3. **Git** installato

## 🛠️ Configurazione Rapida

### 1. Clona il repository (se non l'hai già fatto)
```bash
git clone <repository-url>
cd hyperliquid-ai-trading-bot
```

### 2. Configura le variabili d'ambiente
```bash
# Copia il file di esempio
cp .env.example .env

# Modifica .env con i tuoi valori
nano .env  # oppure usa il tuo editor preferito
```

**Variabili MINIME da configurare in `.env`:**
```env
HYPERLIQUID_WALLET_ADDRESS=0xYourWalletAddressHere
HYPERLIQUID_PRIVATE_KEY=0xYourPrivateKeyHere
OPENROUTER_API_KEY=sk-or-v1-YourOpenRouterAPIKeyHere
DASHBOARD_API_KEY=hyperliquid123-super-secure-key-456
VITE_DASHBOARD_API_KEY=hyperliquid123-super-secure-key-456
```

### 3. Installa le dipendenze
```bash
# Dipendenze Python
pip install -r requirements.txt

# Dipendenze Node.js
npm install
```

## 🧪 Test Rapido della Configurazione

### Opzione A: Test automatico completo
```bash
# Questo script testa tutto
python test_local.py
```

### Opzione B: Test manuale passo-passo

1. **Test dipendenze Python:**
```bash
python3 -c "import requests; import eth_account; import flask; print('✅ Dipendenze OK')"
```

2. **Test dipendenze Node.js:**
```bash
npm list
```

3. **Test file .env:**
```bash
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
required = ['HYPERLIQUID_WALLET_ADDRESS', 'HYPERLIQUID_PRIVATE_KEY', 'DASHBOARD_API_KEY']
missing = [var for var in required if not os.getenv(var)]
print('✅ .env OK' if not missing else f'❌ Mancano: {missing}')
"
```

## 🚀 Avvio Locale

### Metodo 1: Script automatico (raccomandato)
```bash
# Rendi eseguibile lo script
chmod +x run_local.sh

# Avvia tutto
./run_local.sh
```

### Metodo 2: Manuale (2 terminali)

**Terminale 1 - Backend API:**
```bash
python api_server.py
```

**Terminale 2 - Frontend Dashboard:**
```bash
npm run dev
```

## 🌐 Collegamenti

Una volta avviato tutto:
- **Dashboard:** http://localhost:3000
- **API Server:** http://localhost:5000
- **Health Check:** http://localhost:5000/api/health

## 🔧 Risoluzione Problemi

### ❌ "DASHBOARD_API_KEY not set"
Assicurati che `.env` contenga:
```env
DASHBOARD_API_KEY=hyperliquid123-super-secure-key-456
VITE_DASHBOARD_API_KEY=hyperliquid123-super-secure-key-456
```

### ❌ "ModuleNotFoundError"
Installa le dipendenze mancanti:
```bash
pip install -r requirements.txt
npm install
```

### ❌ Porte già in uso
Se le porte 3000 o 5000 sono occupate:
```bash
# Cambia porta API server
API_SERVER_PORT=5001 python api_server.py

# Cambia porta frontend
VITE_PORT=3001 npm run dev
```

### ❌ Errore CORS
Verifica che `CORS_ALLOWED_ORIGINS` in `.env` includa:
```env
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

## 📊 Test del Bot di Trading

### Test singolo ciclo (SICURO - paper trading)
```bash
python hyperliquid_bot_executable_orders.py --single-cycle
```

### Test connessione Hyperliquid
```bash
python scripts/test_connection.py
```

### Verifica posizioni correnti
```bash
python check_current_positions.py
```

## 🎯 Configurazione per Test

Per test sicuri, usa questa configurazione in `.env`:
```env
EXECUTION_MODE=paper
ENABLE_MAINNET_TRADING=false
TRADING_PAIRS=BTC,ETH,SOL
DAILY_NOTIONAL_LIMIT_USD=100
MAX_TRADES_PER_CYCLE=1
```

## 🔐 Sicurezza

**⚠️ IMPORTANTE:**
- **NON** condividere mai il tuo `.env`
- **NON** commitare il `.env` su Git
- Usa `ENABLE_MAINNET_TRADING=true` SOLO quando sei pronto per trading reale
- In modalità `paper` non vengono effettuati ordini reali

## 📈 Monitoraggio

Una volta avviato:
1. **Dashboard:** http://localhost:3000 - monitora in tempo reale
2. **Logs:** `logs/hyperliquid_bot.log` - log dettagliati
3. **API:** http://localhost:5000/api/health - stato del server

## 🆘 Supporto

Se incontri problemi:
1. Controlla i log: `tail -f logs/hyperliquid_bot.log`
2. Verifica le porte: `lsof -i :3000` e `lsof -i :5000`
3. Testa manualmente: `curl -H "X-API-Key: <tua-chiave>" http://localhost:5000/api/health`
4. Riavvia tutto: `pkill -f "python\|npm"` e riprova

Buon testing! 🚀