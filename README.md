# 🤖 Hyperliquid Trading Bot — Dashboard & AI Trading

**Bot di trading automatico su Hyperliquid** alimentato da **Claude Opus 4.6** (OpenRouter). Tutti i dati di mercato provengono **esclusivamente dall'API Hyperliquid**. Include:

- **Analisi Multi-Timeframe** (5m, 1h, 4h): EMA, RSI (Wilder), MACD, Bollinger Bands, VWAP, ATR.
- **Gestione Rischio Avanzata**: SL/TP, Trailing Stop, Break-Even automatico.
- **Dashboard React Live**: Grafici equity, orderbook, posizioni, trade history, logs, circuit breakers.
- **Sicurezza**: Circuit breaker, rate limiting, validazione Decimal, fallback hold.
- **Modalità Paper/Live** con double-check sicurezza.

[![Dashboard Screenshot](frontend/src/assets/dashboard-reference.jpg)](frontend/src/assets/dashboard-reference.jpg)

## 📋 Prerequisiti

- **Python 3.10+**
- **Node.js 18+** (per frontend)
- **Account Hyperliquid** con fondi (testa in paper prima!)
- **Chiave OpenRouter** (per LLM Claude Opus)
- **Git** (opzionale)

## 🚀 Installazione Rapida (5 minuti)

```bash
# 1. Clona il repo
git clone <repo-url>
cd hyperliquid-bot

# 2. Backend Python
pip install -r requirements.txt

# 3. Frontend
cd frontend
npm install
cd ..

# 4. Configurazione .env (CRITICO!)
cp .env.example .env
# Modifica .env con le tue chiavi (vedi sotto)
```

## ⚙️ Configurazione .env (Obbligatoria)

Copia `.env.example` → `.env` e **riempi i valori reali**:

```bash
# Credenziali Hyperliquid (OBBLIGATORIE)
HYPERLIQUID_PRIVATE_KEY=your_private_key_here  # NO 0x prefix!
HYPERLIQUID_WALLET_ADDRESS=0xYourWalletAddress

# LLM (Obbligatorio per AI decisions)
OPENROUTER_API_KEY=sk-or-v1-yourkeyhere

# Modalità (SICUREZZA: double-check!)
EXECUTION_MODE=paper  # paper (test) o live
ENABLE_MAINNET_TRADING=false  # false per test, true solo dopo paper!

# Trading Pairs (modifica a piacere)
TRADING_PAIRS=BTC,ETH,SOL,BNB

# Dashboard API Key (per frontend auth)
DASHBOARD_API_KEY=H9@kL$7mN#pQ2!rT8vY3wX5zB4&cD6*fG1  # Cambiala!

# Resto config (default OK per test)
# ...
```

**⚠️ AVVISO SICUREZZA**:
- **Mai commit .env** (gitignored).
- Testa **sempre** con `EXECUTION_MODE=paper` + `ENABLE_MAINNET_TRADING=false`.
- Live trading: **double-check** wallet/bilancio!

## 🧪 Test di Connessione (Obbligatorio!)

```bash
python scripts/test_connection.py
```

**Output atteso**:
```
✅ VARIABILI D'AMBIENTE OK
✅ WALLET VALIDO
✅ HYPERLIQUID CONNESSO (X asset)
✅ SALDO OK ($XXX)
✅ OPENROUTER OK
✅ TRADING PAIRS OK
🎉 TUTTO OK! Il bot è pronto.
```

Se fallisce → correggi .env e riprova.

## 🎯 Avvio Modalità Test (Single Cycle)

```bash
# Testa UN ciclo (nessun ordine reale)
python hyperliquid_bot_executable_orders.py --single-cycle
```

**Output atteso**:
```
CYCLE #1: Analyzing BTC → LLM decision → HOLD (paper mode)
✅ Cycle completato senza errori
```

## 🚀 Avvio Completo (Produzione)

**3 Terminali paralleli**:

### Terminal 1: Bot Principale
```bash
python hyperliquid_bot_executable_orders.py
```
- Cicli ogni 60-300s (adattivo).
- Logs JSON in `logs/hyperliquid_bot.log`.

### Terminal 2: API Server (Backend Dashboard)
```bash
python api_server.py
```
- Serve `/api/*` su `http://127.0.0.1:5000`.
- Metrics Prometheus: `http://127.0.0.1:5000/metrics`.

### Terminal 3: Frontend Dashboard
```bash
cd frontend
npm run dev
```
- Dashboard live: **http://localhost:3000**.
- Grafici realtime, orderbook, posizioni, logs.

## 📊 Dashboard (http://localhost:3000)

| Sezione | Cosa Vede |
|---------|-----------|
| **Header** | Status bot (Running/Stopped), coin corrente |
| **Stats** | Balance, PnL, Margin, Win Rate, Cycle # |
| **Drawdown Bar** | Drawdown attuale vs max (rosso se >70%) |
| **Price Chart** | Candlestick realtime (Lightweight Charts) + Orderbook |
| **Equity Curve** | Grafico valore portfolio reale (snapshots) |
| **Positions** | Posizioni aperte + managed (SL/TP/BE) |
| **Trade History** | Tabella trade con filtro coin/export CSV |
| **Circuit Breakers** | Stato API (OPEN=blocked) |
| **Logs** | Logs realtime (filter ERROR/INFO) |

**API Key**: Frontend legge da meta tag (sync con .env). Se 401 → check `DASHBOARD_API_KEY`.

## 🛑 Gestione & Stop

- **Graceful Shutdown**: `Ctrl+C` → salva stato, notifica Telegram.
- **Monitor Logs**: `tail -f logs/hyperliquid_bot.log`
- **Metrics**: `curl http://127.0.0.1:5000/metrics`
- **Reset Metrics**: Bot resetta contatori giornalieri.
- **Emergency**: Se margin >85% → chiude worst position automaticamente.

## 🔧 Comandi Utili (Scripts)

```bash
# Test singolo ciclo
./scripts/run_single_cycle.sh

# Avvio tutto (bot + API + frontend)
./scripts/start_bot.sh

# Chiudi posizione SOL (utility)
python close_sol_position.py

# Check posizioni correnti
python check_current_positions.py

# Ordine minimale test
python hyperliquid_minimal_order.py
```

## ⚠️ Sicurezza & Best Practices

1. **TESTA SEMPRE IN PAPER**: `EXECUTION_MODE=paper`.
2. **Live Trading**:
   - Inizia con `DAILY_NOTIONAL_LIMIT_USD=100`.
   - Monitora **primi 24h** manualmente.
   - **Mai** leverage >10x.
3. **Risorse**:
   - Costo LLM: ~$0.03/chiamata Opus → $5-10/giorno (20 pairs).
   - Telegram: Abilita in .env per alert SL/TP/emergency.
4. **Backup**:
   - Stato persistente: `state/*.json` (gitignored).
   - Gitignore: .env, logs, state.

## 🐛 Troubleshooting

| Errore | Soluzione |
|--------|-----------|
| `401 Unauthorized` | Check `DASHBOARD_API_KEY` in .env + rebuild frontend |
| `Hyperliquid timeout` | Check internet/VPN |
| `No LLM response` | Check `OPENROUTER_API_KEY` + credito |
| `Wallet mismatch` | Verifica private_key → address con `test_connection.py` |
| `Dashboard vuota` | Avvia `api_server.py` prima del frontend |
| `Paper orders only` | `ENABLE_MAINNET_TRADING=true` + `EXECUTION_MODE=live` |

## 📖 Riferimenti

- **Regole AI**: [AI_RULES.md](AI_RULES.md)
- **Architettura**: [session_report.md](session_report.md)
- **Test**: `tests/` (pytest-ready)
- **Docker**: Dockerfile pronto (builda tutto).

**Autori**: AI Editor (Dyad) + Regole Hyperliquid.

---

**Pronto per il trading?** Esegui `python scripts/test_connection.py` → se OK, avvia! 🚀