# 🤖 Hyperliquid Trading Bot

**AI-Powered Trading Bot for Hyperliquid** | Claude Opus 4.6 | Real-time Dashboard

## 🚀 QUICK START (3 MINUTI)

### 1. Installa
```bash
pip install -r requirements.txt
npm install
```

### 2. Configura .env (COPIA E MODIFICA)
```bash
cp .env.example .env
```
**APRI `.env` e COMPILA SOLO QUESTI**:
```
HYPERLIQUID_WALLET_ADDRESS=0xIlTuoWallet
HYPERLIQUID_PRIVATE_KEY=0xLaTuaChiavePrivata
OPENROUTER_API_KEY=sk-or-LaTuaChiaveOpenRouter
DASHBOARD_API_KEY=hyperliquid123-super-secure-key-456
```

### 3. Test Configurazione
```bash
python scripts/test_connection.py
```
✅ **Tutti verdi?** Procedi!

### 4. Test Singolo Ciclo (SICURO)
```bash
python hyperliquid_bot_executable_orders.py --single-cycle
```

### 5. AVVIA (3 TERMINALI)
```
# TERMINALE 1: BOT
python hyperliquid_bot_executable_orders.py

# TERMINALE 2: API SERVER
python api_server.py

# TERMINALE 3: DASHBOARD
npm run dev
```

✅ **Dashboard**: [http://localhost:3000](http://localhost:3000)

## ✅ DASHBOARD_API_KEY CHECK

Assicurati che `.env` contenga:
```
DASHBOARD_API_KEY=...
```

In sviluppo, Vite inoltra automaticamente questa chiave all’API backend via proxy (`X-API-Key`).

Poi riavvia `api_server.py` e `npm run dev`.

## 🛠️ Risoluzione Problemi Comuni

| ❌ Errore | ✅ Soluzione |
|-----------|-------------|
| `DASHBOARD_API_KEY not set` | Imposta `DASHBOARD_API_KEY` nel `.env` |
| Dashboard vuota | Avvia `python api_server.py` (Terminale 2) |
| 401 Unauthorized | Verifica `DASHBOARD_API_KEY` e riavvia backend/frontend |
| No trades | `EXECUTION_MODE=live` + `ENABLE_MAINNET_TRADING=true` |

## 📊 Dashboard Live

| Sezione | Cosa vedi |
|---------|-----------|
| **Stats** | Balance • PnL • Margin • Win Rate |
| **Drawdown** | Barra rossa >8% (stop automatico 12%) |
| **TradingView** | Candele live + Orderbook |
| **Equity** | Curva portfolio reale |
| **Risk Mgmt** | SL/TP/Trailing/BE attivi |
| **Trades** | Storia + AI reasoning + CSV Export |

## ⚙️ Configurazione Principale (.env)

```
# MODALITÀ TRADING
EXECUTION_MODE=paper     # paper (sicuro) / live (reale)
ENABLE_MAINNET_TRADING=false  # ⚠️ true = SOLDI VERI!

# RISCHIO
MAX_DRAWDOWN_PCT=0.12    # Stop 12%
DAILY_NOTIONAL_LIMIT_USD=500
MAX_ORDER_MARGIN_PCT=0.10
MAX_ORDER_NOTIONAL_USD=0

# STRATEGIA TREND
TREND_SL_PCT=0.04
TREND_TP_PCT=0.08
TREND_BREAK_EVEN_ACTIVATION_PCT=0.02

# LLM
LLM_MODEL=anthropic/claude-opus-4.6
LLM_TEMPERATURE=0.2
```

**Completa**: `.env.example`

## 🛡️ Protezioni Automatiche

- **Paper Mode** (default)
- **Drawdown 12%** → Stop trading
- **Margin 85%** → Chiude peggior posizione
- **Circuit Breakers** → API down = stop
- **Correlazione** → Blocca BTC+ETH long
- **Fill Verification** → Conferma ordini eseguiti

## 📱 Telegram (Opzionale)
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```
Alert: trades, SL/TP, emergenze.

## 🧪 Script Utili
```bash
python scripts/test_connection.py     # Test tutto
python close_sol_position.py          # Chiudi SOL emergenza
python check_current_positions.py     # Vedi posizioni
```

## 🏃‍♂️ Production (Background)
```bash
python hyperliquid_bot_executable_orders.py
python api_server.py
npm run dev
```

**Stop**: `Ctrl+C` o `kill -SIGTERM <pid>`

## 📈 Costi
- **LLM**: dipende dal modello e dal numero di chiamate
- **Hyperliquid**: Fee normali maker/taker

**Scalabile**: `DEFAULT_CYCLE_SEC=300` → dimezza costi.

## 📄 Licenza
MIT — Free uso personale/commerciale.

**Buon Trading! 🚀🇮🇹**