# 🚀 Guida Rapida - Hyperliquid Trading Bot

## 📋 Prerequisiti
- **Python 3.10+** (https://www.python.org/downloads/)
- **Node.js 18+** (https://nodejs.org/)
- **Git** (https://git-scm.com/)

## ⚡ Installazione Rapida (Windows)

### 1. Installa tutte le dipendenze
```cmd
install_deps.bat
```

### 2. Configura le variabili d'ambiente
```cmd
copy .env.example .env
```

**APRI `.env` E MODIFICA QUESTE VARIABILI:**
```env
HYPERLIQUID_WALLET_ADDRESS=0xYourWalletAddressHere
HYPERLIQUID_PRIVATE_KEY=0xYourPrivateKeyHere
OPENROUTER_API_KEY=sk-or-v1-YourOpenRouterAPIKeyHere
DASHBOARD_API_KEY=hyperliquid123-super-secure-key-456
VITE_DASHBOARD_API_KEY=hyperliquid123-super-secure-key-456
```

## 🚀 Avvio Rapido

### Metodo 1: Script automatico
```cmd
run_local.sh
```

### Metodo 2: Manuale (2 terminali)

**Terminale 1 - Backend API:**
```cmd
python api_server.py
```

**Terminale 2 - Frontend Dashboard:**
```cmd
npm run dev
```

## 🌐 Collegamenti
- **Dashboard:** http://localhost:3000
- **API Server:** http://localhost:5000
- **Health Check:** http://localhost:5000/api/health

## 🧪 Test Configurazione
```cmd
python test_local.py
```

## 📊 Test Bot Trading (Paper Mode)
```cmd
python hyperliquid_bot_executable_orders.py --single-cycle
```

## 🔧 Risoluzione Problemi Comuni

### ❌ "ModuleNotFoundError"
```cmd
pip install -r requirements.txt
npm install --force
```

### ❌ Porte occupate
Cambia porte in `.env`:
```env
API_SERVER_PORT=5001
VITE_PORT=3001
```

### ❌ Errori npm su Windows
Esegui PowerShell come Amministratore:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
npm cache clean --force
npm install --force
```

## ⚙️ Configurazione Minima per Test
In `.env` usa:
```env
EXECUTION_MODE=paper
ENABLE_MAINNET_TRADING=false
TRADING_PAIRS=BTC,ETH,SOL
DAILY_NOTIONAL_LIMIT_USD=100
```

## 📞 Supporto
1. Controlla logs: `logs/hyperliquid_bot.log`
2. Test API: `curl http://localhost:5000/api/health`
3. Riavvia tutto: Chiudi terminali e riavvia

**Buon testing! 🚀**