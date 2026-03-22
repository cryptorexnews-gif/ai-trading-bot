# 🤖 Hyperliquid AI Trading Bot

Bot di trading automatico per Hyperliquid con dashboard React in tempo reale, analisi multi-timeframe e gestione rischio integrata.

## ✅ Cosa fa questo progetto

- Trading AI con modello `anthropic/claude-opus-4.6` via OpenRouter
- Dati di mercato **solo da Hyperliquid** (nessuna fonte esterna)
- Strategia trend multi-timeframe (1H/4H/1D)
- Risk management automatico (SL/TP, trailing, break-even, drawdown, correlazione)
- Dashboard live con:
  - stato bot
  - posizioni
  - trade history
  - equity/performance
  - chart candele + indicatori
  - logs + circuit breaker + metriche

---

## 📦 Requisiti

- Python 3.10+
- Node.js 18+
- npm

---

## ⚙️ Setup rapido

### 1) Installa dipendenze

```bash
pip install -r requirements.txt
npm install
```

### 2) Configura variabili ambiente

Crea `.env` partendo dal template e imposta almeno queste chiavi:

```env
HYPERLIQUID_WALLET_ADDRESS=0x...
HYPERLIQUID_PRIVATE_KEY=0x...
OPENROUTER_API_KEY=sk-or-...
DASHBOARD_API_KEY=una-chiave-lunga-e-casuale
```

### 3) Verifica configurazione

```bash
python scripts/test_connection.py
```

---

## 🚀 Avvio locale (3 processi)

### Terminale 1 — Bot

```bash
python hyperliquid_bot_executable_orders.py
```

### Terminale 2 — API server

```bash
python api_server.py
```

### Terminale 3 — Dashboard frontend

```bash
npm run dev
```

Apri: **http://localhost:3000**

---

## 🧪 Test sicuro prima della produzione

Esegui prima un ciclo singolo:

```bash
python hyperliquid_bot_executable_orders.py --single-cycle
```

---

## 🔐 Sicurezza operativa (IMPORTANTISSIMO)

- `EXECUTION_MODE=paper` = simulazione (consigliato per test)
- `EXECUTION_MODE=live` + `ENABLE_MAINNET_TRADING=true` = ordini reali
- In live:
  - usa API key robuste
  - non condividere mai `.env`
  - limita esposizione e leverage
  - verifica sempre dashboard e log

---

## 🧠 Strategia (sintesi)

- Trend principale su 4H
- Conferma su 1D
- Timing entrata su 1H
- Filtri su volume/RSI/struttura trend
- Chiusure automatiche via SL/TP/trailing/break-even
- Blocco trade in caso di rischio correlazione o violazione limiti

---

## 📊 Endpoint utili

- `GET /api/health` → health check pubblico
- `GET /api/status` → stato bot
- `GET /api/portfolio` → portafoglio/posizioni
- `GET /api/trades` → storico trade
- `GET /api/performance` → metriche e curve
- `GET /api/candles` → dati chart
- `GET /metrics` → export Prometheus

> Gli endpoint protetti richiedono `X-API-Key: DASHBOARD_API_KEY`.

---

## 🛠️ Troubleshooting veloce

### Dashboard vuota o dati mancanti
- Verifica che `api_server.py` sia avviato
- Verifica `DASHBOARD_API_KEY` in `.env`
- Riavvia backend e frontend

### Errori 401 Unauthorized
- API key assente o errata
- Controlla header e variabile `DASHBOARD_API_KEY`

### Errori 429 rate_limited
- Troppo polling concorrente dalla dashboard
- Riduci frequenza refresh o apri meno tab contemporaneamente

### Nessun trade eseguito
- Potresti essere in `paper` o in fase `hold` per filtri rischio
- Controlla se `ENABLE_MAINNET_TRADING=true` (solo se vuoi live)

### Coin non riconosciuta in chart
- La coin potrebbe non essere nella lista runtime o nelle pair abilitate
- Salva la coin dalla sezione runtime controls

---

## 🗂️ Struttura progetto (alto livello)

- `hyperliquid_bot_executable_orders.py` → entrypoint bot
- `cycle_orchestrator.py` → logica ciclo trading
- `exchange_client.py` → client Hyperliquid + firma ordini
- `llm_engine.py` → integrazione OpenRouter
- `risk_manager.py` / `position_manager.py` → gestione rischio
- `api/` → server Flask + endpoints dashboard
- `src/` → frontend React + chart + pagine dashboard
- `state/` → stato runtime persistito (json atomici)

---

## 📁 File di stato runtime

Generati automaticamente sotto `state/`:

- `bot_state.json`
- `bot_metrics.json`
- `bot_live_status.json`
- `managed_positions.json`
- `runtime_config.json`

---

## 🧾 Note operative

- I log sono strutturati JSON
- Le scritture file stato sono atomiche
- I calcoli finanziari usano `Decimal`
- Circuit breaker/rate limiter sono attivi lato API e client

---

## 📌 Best practice consigliate

1. Parti sempre in `paper`
2. Esegui `--single-cycle` dopo ogni modifica importante
3. Passa a `live` solo dopo validazione completa
4. Monitora dashboard + log nei primi cicli live
5. Mantieni limiti rischio conservativi

---

## 📄 Licenza

MIT