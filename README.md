# 🤖 Hyperliquid Trading Bot

**AI-Powered Trading Bot for Hyperliquid** | Claude Opus 4.6 | Real-time Dashboard | **Trend 4H/1D Ultra-Conservativo**

## 🚀 QUICK START (3 MINUTI)

### 1. Installa
```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
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
VITE_DASHBOARD_API_KEY=hyperliquid123-super-secure-key-456  # STESSA CHIAVE!
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
# TERMINALE 1: BOT (Trend 4H/1D Ultra-Conservativo)
python hyperliquid_bot_executable_orders.py

# TERMINALE 2: API SERVER
python api_server.py

# TERMINALE 3: DASHBOARD
cd frontend && npm run dev
```

✅ **Dashboard**: [http://localhost:3000](http://localhost:3000)

## ✅ DASHBOARD_API_KEY AUTO-FIX

**Il tuo errore è RISOLTO**:
```
🚀 DASHBOARD_API_KEY AUTO-GENERATED (add to .env):
   DASHBOARD_API_KEY=abc123XYZ-super-secure-key-456def789
   VITE_DASHBOARD_API_KEY=abc123XYZ-super-secure-key-456def789
```

**COPIA la chiave generata nel tuo `.env`** (stessa per entrambe le righe) e **riavvia** `api_server.py`.

## 🛠️ Risoluzione Problemi Comuni

| ❌ Errore | ✅ Soluzione |
|-----------|-------------|
| `DASHBOARD_API_KEY not set` | Copia chiave generata da log → `.env` → riavvia |
| Dashboard vuota | `python api_server.py` (Terminale 2) |
| 401 Unauthorized | **STESSA CHIAVE** in `DASHBOARD_API_KEY` + `VITE_DASHBOARD_API_KEY` |
| No trades | `EXECUTION_MODE=live` + `ENABLE_MAINNET_TRADING=true` |

## 📊 Dashboard Live

| Sezione | Cosa vedi |
|---------|-----------|
| **Stats** | Balance • PnL • Margin • Win Rate |
| **Drawdown** | Barra rossa >8% (stop automatico 10%) |
| **TradingView** | Candele live + Orderbook (default 4H) |
| **Equity** | Curva portfolio reale |
| **Risk Mgmt** | SL/TP/Trailing/BE attivi |
| **Trades** | Storia + AI reasoning + CSV Export |

## ⚙️ Configurazione Trend 4H/1D Ultra-Conservativa (.env)

```
# MODALITÀ TRADING
EXECUTION_MODE=paper     # paper (sicuro) / live (reale)
ENABLE_MAINNET_TRADING=false  # ⚠️ true = SOLDI VERTI!

# RISCHIO ULTRA-CONSERVATIVO
MAX_DRAWDOWN_PCT=0.10    # Stop a 10% drawdown (molto protettivo)
DAILY_NOTIONAL_LIMIT_USD=600  # Limite giornaliero 600 USD

# STRATEGIA TREND 4H/1D ULTRA-CONSERVATIVA
PRIMARY_TIMEFRAME=4h     # Trend primario
SECONDARY_TIMEFRAME=1d   # Trend principale
ENTRY_TIMEFRAME=1h       # Timing entrata
MIN_TREND_DURATION_HOURS=36  # Trend deve durare 36 ore
VOLUME_CONFIRMATION_THRESHOLD=1.6  # Volume 1.6x sopra media
MAX_TREND_POSITIONS=2    # Max 2 posizioni trend
TREND_POSITION_SIZE_PCT=0.02  # 2% portfolio per posizione (molto conservativo)
TREND_SL_PCT=0.04        # Stop Loss 4% per trend
TREND_TP_PCT=0.08        # Take Profit 8% (R:R 1:2)
TREND_BREAK_EVEN_ACTIVATION_PCT=0.02  # BE @ +2%
TREND_TRAILING_ACTIVATION_PCT=0.03    # Trailing @ +3%
TREND_TRAILING_CALLBACK=0.02  # Callback 2%

# CICLO ANALISI OTTIMIZZATO
DEFAULT_CYCLE_SEC=1800   # 30 minuti (ottimale per trend 4H/1D)
MIN_CYCLE_SEC=900        # Minimo 15 minuti
MAX_CYCLE_SEC=3600       # Massimo 60 minuti
```

**Completa**: `.env.example`

## 🛡️ Protezioni Automatiche Ultra-Conservative

- **Paper Mode** (default)
- **Drawdown 10%** → Stop trading immediato
- **Margin 65%** → Ampio margine di sicurezza
- **Position Size 2%** → Esposizione minima per trade
- **Leverage 4x max** → Molto conservativo
- **Confidence 78% min** → Altamente selettivo
- **Circuit Breakers** → API down = stop
- **Correlazione** → Blocca posizioni correlate
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
nohup python hyperliquid_bot_executable_orders.py > bot.log 2>&1 &
python api_server.py
cd frontend && npm run dev
```

**Stop**: `Ctrl+C` o `kill -SIGTERM <pid>`

## 📈 Costi
- **LLM**: ~$0.03/call → ~$10/giorno (20 pairs)
- **Hyperliquid**: Fee normali maker/taker

**Scalabile**: `DEFAULT_CYCLE_SEC=1800` → 30 minuti ottimale per trend.

## 📄 Licenza
MIT — Free uso personale/commerciale.

**Buon Trading! 🚀🇮🇹**