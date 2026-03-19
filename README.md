# 🤖 Hyperliquid AI Trading Bot

Bot di trading automatizzato per **Hyperliquid**, alimentato da **Claude Opus 4.6** via OpenRouter. Tutti i dati di mercato provengono esclusivamente dall'API Hyperliquid.

---

## 🚀 Quick Start — Avvio Rapido

### Prerequisiti

- **Python 3.10+** — [Download](https://www.python.org/downloads/)
- **Node.js 18+** — [Download](https://nodejs.org/) (solo per la dashboard)
- **Wallet Hyperliquid** con fondi depositati (per live trading)
- **API Key OpenRouter** — [Registrati](https://openrouter.ai/) (per Claude Opus 4.6)

### Step 1: Clona e installa

```bash
# Clona il repository
git clone <repository-url>
cd hyperliquid-ai-trading-bot

# Crea ambiente virtuale Python
python -m venv venv

# Attiva l'ambiente (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Attiva l'ambiente (Windows CMD)
venv\Scripts\activate.bat

# Attiva l'ambiente (Linux/Mac)
source venv/bin/activate

# Installa dipendenze Python
pip install -r requirements.txt
```

### Step 2: Configura il file `.env`

Copia il template e compila i tuoi dati:

```bash
cp .env.example .env
```

Apri `.env` con un editor e compila **3 valori obbligatori**:

```bash
# OBBLIGATORIO: La tua chiave privata Hyperliquid
HYPERLIQUID_PRIVATE_KEY=la_tua_chiave_privata_qui

# OBBLIGATORIO: Il tuo indirizzo wallet (deve corrispondere alla chiave privata)
HYPERLIQUID_WALLET_ADDRESS=0xIlTuoIndirizzoWallet

# OBBLIGATORIO: API key OpenRouter per Claude Opus 4.6
OPENROUTER_API_KEY=la_tua_api_key_openrouter

# OPZIONALE: Scegli le monete da monitorare (default: 20 coin)
TRADING_PAIRS=BTC,ETH,SOL,BNB,XRP

# OPZIONALE: Ciclo di trading (default: 60 secondi)
DEFAULT_CYCLE_SEC=900
ENABLE_ADAPTIVE_CYCLE=false
```

### Step 3: Test rapido (Paper Mode)

```bash
# Esegui un singolo ciclo di test (nessun ordine reale)
python hyperliquid_bot_executable_orders.py --single-cycle
```

Se vedi `"Cycle #1 complete"` nel log, il bot funziona! ✅

### Step 4: Avvia il bot in continuo

```bash
# Trading continuo in paper mode (simulato)
python hyperliquid_bot_executable_orders.py
```

Per fermare: premi `Ctrl+C` (shutdown graceful).

### Step 5: Avvia la Dashboard (opzionale)

Apri **3 terminali separati**:

```bash
# Terminale 1: Bot di trading
python hyperliquid_bot_executable_orders.py

# Terminale 2: Server API per la dashboard
python api_server.py

# Terminale 3: Frontend React
cd frontend
npm install
npm run dev
```

Apri **http://localhost:3000** nel browser 🎉

---

## ⚠️ Passare al Live Trading

> **ATTENZIONE**: Il live trading usa soldi veri. Testa sempre in paper mode prima!

Per abilitare il trading reale, modifica `.env`:

```bash
EXECUTION_MODE=live
ENABLE_MAINNET_TRADING=true
```

Il bot verificherà automaticamente che il wallet address corrisponda alla chiave privata all'avvio.

---

## 📊 Caratteristiche

| Feature | Descrizione |
|---------|-------------|
| **AI Trading** | Claude Opus 4.6 analizza indicatori tecnici multi-timeframe |
| **20 Coin** | BTC, ETH, SOL, BNB, ADA, DOGE, XRP, AVAX, LINK, SUI, ARB, OP, NEAR, WIF, PEPE, INJ, TIA, SEI, RENDER, FET |
| **Stop-Loss** | 3% predefinito, configurabile |
| **Take-Profit** | 5% predefinito, configurabile |
| **Trailing Stop** | 2% callback, attivazione dopo +2% profitto |
| **Break-Even** | Sposta SL a entry+0.1% dopo +1.5% profitto |
| **Correlazione** | Previene posizioni correlate nella stessa direzione |
| **Emergency De-Risk** | Chiude posizione peggiore se margine > 88% |
| **Dashboard** | Chart real-time, order book, posizioni, trade history |
| **Telegram** | Notifiche per trade, SL/TP, errori |
| **Prometheus** | Metriche su `/metrics` per Grafana |

---

## 🏗️ Architettura

```
┌─────────────────────────────────────────────────────────┐
│                    Dashboard React                       │
│  (TradingView Chart + Order Book, Positions, Trades)    │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP (polling ogni 5s)
┌──────────────────────▼──────────────────────────────────┐
│              API Server (Flask Blueprints)                │
│  api/routes: health, bot, trading, market, logs, metrics │
└──────────────────────┬──────────────────────────────────┘
                       │ Legge file JSON condivisi
┌──────────────────────▼──────────────────────────────────┐
│              Bot Process                                 │
│                                                           │
│  BotConfig ──→ HyperliquidBot ──→ CycleOrchestrator     │
│                                                           │
│  Fasi per ciclo:                                          │
│    1. Health check                                        │
│    2. Portfolio snapshot (PortfolioService)               │
│    3. SL/TP/Trailing/Break-even (PositionManager)        │
│    4. Emergency de-risk (RiskManager)                    │
│    5. Correlazione asset (CorrelationEngine)             │
│    6. Per-coin: technicals → LLM → risk → execute       │
│    7. Persistenza stato (StateStore)                     │
└──────────────────────────────────────────────────────────┘
```

---

## 💰 Costi Stimati

| Componente | Costo |
|-----------|-------|
| **OpenRouter (Claude Opus 4.6)** | ~$0.50-2/giorno con 5 coin e ciclo 15min |
| **Hyperliquid** | Nessun costo API, solo commissioni trading |
| **Server** | Qualsiasi VPS da $5/mese o il tuo PC |

---

## 🔒 Sicurezza

- La chiave privata non viene mai salvata come attributo — solo l'oggetto `Account` derivato
- API key OpenRouter solo negli header della sessione HTTP
- Dashboard protetta con `DASHBOARD_API_KEY` (opzionale)
- File di stato con permessi `0o600` (solo proprietario)
- Log sanitizzati prima di essere serviti alla dashboard
- Wallet address validato contro la chiave privata all'avvio

---

## 📋 Variabili d'Ambiente Principali

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `EXECUTION_MODE` | `paper` | `paper` o `live` |
| `TRADING_PAIRS` | 20 coin | Coin separate da virgola |
| `DEFAULT_CYCLE_SEC` | `60` | Secondi tra cicli |
| `ENABLE_ADAPTIVE_CYCLE` | `true` | Ciclo adattivo alla volatilità |
| `DEFAULT_SL_PCT` | `0.03` | Stop-loss 3% |
| `DEFAULT_TP_PCT` | `0.05` | Take-profit 5% |
| `HARD_MAX_LEVERAGE` | `10` | Leverage massimo |
| `MAX_DRAWDOWN_PCT` | `0.15` | Drawdown massimo 15% |
| `DAILY_NOTIONAL_LIMIT_USD` | `1000` | Limite notionale giornaliero |

Vedi `.env.example` per la lista completa.

---

## 🧪 Test

```bash
# Esegui tutti i test
python -m pytest tests/ -v

# Oppure singolarmente
python tests/test_models.py
python tests/test_risk_manager.py
python tests/test_technical_indicators.py
python tests/test_decimals.py
python tests/test_state_store.py
```

---

## ⚠️ Disclaimer

Questo software è fornito come-è senza garanzia. Il trading di criptovalute è altamente rischioso e può risultare in perdita totale di fondi. Testa sempre in paper mode e non rischiare mai più di quanto puoi permetterti di perdere.