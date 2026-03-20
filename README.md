# 🤖 Hyperliquid AI Trading Bot

Bot di trading automatizzato per l'exchange **Hyperliquid**, alimentato da **Claude Opus 4** via OpenRouter. Tutti i dati di mercato provengono esclusivamente dall'API Hyperliquid — nessuna fonte esterna.

---

## 📋 Indice

1. [Prerequisiti](#-prerequisiti)
2. [Installazione](#-installazione)
3. [Configurazione](#-configurazione)
4. [Primo Avvio (Test)](#-primo-avvio-test)
5. [Avvio in Produzione](#-avvio-in-produzione)
6. [Dashboard Web](#-dashboard-web)
7. [Passare al Trading Reale](#-passare-al-trading-reale)
8. [Gestione del Bot](#-gestione-del-bot)
9. [Strategia di Trading](#-strategia-di-trading)
10. [Notifiche Telegram](#-notifiche-telegram)
11. [Monitoraggio e Metriche](#-monitoraggio-e-metriche)
12. [Variabili d'Ambiente](#-variabili-dambiente)
13. [Test Automatici](#-test-automatici)
14. [Struttura del Progetto](#-struttura-del-progetto)
15. [Architettura](#-architettura)
16. [Risoluzione Problemi](#-risoluzione-problemi)
17. [Costi Stimati](#-costi-stimati)
18. [Sicurezza](#-sicurezza)
19. [Disclaimer](#-disclaimer)

---

## 🔧 Prerequisiti

Prima di iniziare, assicurati di avere:

| Requisito | Versione | Link |
|-----------|----------|------|
| **Python** | 3.10 o superiore | [python.org](https://www.python.org/downloads/) |
| **Node.js** | 18 o superiore (solo per la dashboard) | [nodejs.org](https://nodejs.org/) |
| **Wallet Hyperliquid** | Con fondi depositati | [app.hyperliquid.xyz](https://app.hyperliquid.xyz/) |
| **API Key OpenRouter** | Per Claude Opus 4 | [openrouter.ai](https://openrouter.ai/) |

### Come ottenere la chiave privata Hyperliquid

1. Vai su [app.hyperliquid.xyz](https://app.hyperliquid.xyz/)
2. Connetti il tuo wallet (MetaMask, Rabby, ecc.)
3. Deposita fondi (USDC) sul Layer 2 di Hyperliquid
4. La chiave privata è quella del wallet che hai connesso
5. **Non condividere MAI la tua chiave privata con nessuno**

### Come ottenere la API Key OpenRouter

1. Registrati su [openrouter.ai](https://openrouter.ai/)
2. Vai su **Keys** nel menu
3. Crea una nuova API key
4. Ricarica il credito (minimo consigliato: $5)

---

## 📦 Installazione

### Passo 1: Clona il repository

```bash
git clone <url-del-repository>
cd hyperliquid-ai-trading-bot
```

### Passo 2: Crea un ambiente virtuale Python

```bash
# Crea l'ambiente virtuale
python -m venv venv
```

Attiva l'ambiente virtuale:

```bash
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Windows (CMD)
venv\Scripts\activate.bat

# Linux / macOS
source venv/bin/activate
```

> ⚠️ **Importante**: Attiva sempre l'ambiente virtuale prima di eseguire qualsiasi comando Python del bot.

### Passo 3: Installa le dipendenze Python

```bash
pip install -r requirements.txt
```

### Passo 4: Crea le directory necessarie

```bash
# Linux / macOS
mkdir -p state logs

# Windows (PowerShell)
New-Item -ItemType Directory -Force -Path state, logs
```

---

## ⚙️ Configurazione

### Passo 1: Crea il file `.env`

Copia il template e aprilo con un editor di testo:

```bash
cp .env.example .env
```

### Passo 2: Compila i campi obbligatori

Apri il file `.env` e inserisci questi **3 valori obbligatori**:

```bash
# ═══════════════════════════════════════════════════
# OBBLIGATORIO: Chiave privata del tuo wallet Hyperliquid
# È la chiave privata del wallet che hai connesso su app.hyperliquid.xyz
# Formato: 0x seguito da 64 caratteri esadecimali
# ═══════════════════════════════════════════════════
HYPERLIQUID_PRIVATE_KEY=0x_la_tua_chiave_privata_qui

# ═══════════════════════════════════════════════════
# OBBLIGATORIO: Indirizzo del tuo wallet
# Deve corrispondere alla chiave privata sopra
# Formato: 0x seguito da 40 caratteri esadecimali
# ═══════════════════════════════════════════════════
HYPERLIQUID_WALLET_ADDRESS=0xIlTuoIndirizzoWallet

# ═══════════════════════════════════════════════════
# OBBLIGATORIO: API key di OpenRouter per Claude Opus 4
# Ottienila su https://openrouter.ai/
# ═══════════════════════════════════════════════════
OPENROUTER_API_KEY=sk-or-la-tua-api-key
```

### Passo 3: Personalizza le impostazioni (opzionale)

```bash
# ─── Monete da monitorare ─────────────────────────
# Separa con virgola. Default: 20 monete principali
TRADING_PAIRS=BTC,ETH,SOL,BNB,XRP

# ─── Intervallo tra i cicli (secondi) ────────────
# Più basso = più reattivo ma più costoso in API LLM
DEFAULT_CYCLE_SEC=120

# ─── Ciclo adattivo alla volatilità ──────────────
# true = il bot accelera/rallenta in base alla volatilità
ENABLE_ADAPTIVE_CYCLE=true

# ─── Modalità di esecuzione ──────────────────────
# paper = ordini simulati (sicuro per test)
# live = ordini reali (richiede ENABLE_MAINNET_TRADING=true)
EXECUTION_MODE=paper
```

### Passo 4: Verifica la configurazione

Esegui lo script di test per verificare che tutto sia configurato correttamente:

```bash
python scripts/test_connection.py
```

Questo script verifica:
- ✅ Variabili d'ambiente configurate
- ✅ Corrispondenza wallet/chiave privata
- ✅ Connessione API Hyperliquid
- ✅ Saldo wallet
- ✅ Connessione OpenRouter
- ✅ Trading pairs valide
- ✅ Directory e permessi

Se tutti i test passano, sei pronto per avviare il bot! 🎉

---

## 🚀 Primo Avvio (Test)

### Ciclo singolo di test

Esegui un singolo ciclo per verificare che tutto funzioni:

```bash
python hyperliquid_bot_executable_orders.py --single-cycle
```

Cosa succede:
1. Il bot si connette a Hyperliquid
2. Recupera il tuo saldo e le posizioni aperte
3. Analizza gli indicatori tecnici per ogni moneta configurata
4. Chiede a Claude Opus 4 una decisione di trading
5. Simula l'ordine (in modalità paper)
6. Salva lo stato e si ferma

Se vedi `"Cycle #1 complete"` nei log, il bot funziona correttamente! ✅

### Cosa controllare nei log

- **`Portfolio: balance=$XXX`** — Il tuo saldo è stato letto correttamente
- **`LLM decision for BTC: action=hold`** — Claude ha risposto con una decisione
- **`PAPER order`** — L'ordine è stato simulato (non reale)
- **Nessun errore rosso** — Tutto funziona

---

## 🏃 Avvio in Produzione

### Avvio continuo

```bash
python hyperliquid_bot_executable_orders.py
```

Il bot eseguirà cicli continui ogni 120 secondi (configurabile). Per fermarlo in modo sicuro:

- Premi **`Ctrl+C`** — Il bot salverà lo stato e si fermerà in modo pulito
- Il bot gestisce i segnali SIGINT e SIGTERM per uno shutdown graceful

### Avvio in background (Linux/macOS)

```bash
# Con nohup
nohup python hyperliquid_bot_executable_orders.py > /dev/null 2>&1 &

# Con screen
screen -S trading-bot
python hyperliquid_bot_executable_orders.py
# Premi Ctrl+A poi D per staccare la sessione
# Per riattaccare: screen -r trading-bot

# Con tmux
tmux new -s trading-bot
python hyperliquid_bot_executable_orders.py
# Premi Ctrl+B poi D per staccare
# Per riattaccare: tmux attach -t trading-bot
```

### Avvio come servizio systemd (Linux)

Crea il file `/etc/systemd/system/hyperliquid-bot.service`:

```ini
[Unit]
Description=Hyperliquid AI Trading Bot
After=network.target

[Service]
Type=simple
User=il_tuo_utente
WorkingDirectory=/percorso/del/bot
ExecStart=/percorso/del/bot/venv/bin/python hyperliquid_bot_executable_orders.py
Restart=on-failure
RestartSec=30
Environment=PATH=/percorso/del/bot/venv/bin

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable hyperliquid-bot
sudo systemctl start hyperliquid-bot

# Controlla lo stato
sudo systemctl status hyperliquid-bot

# Vedi i log
sudo journalctl -u hyperliquid-bot -f
```

---

## 🖥️ Dashboard Web

La dashboard mostra in tempo reale: grafico candele, posizioni, trade, equity curve, log e stato del bot.

### Avvio della Dashboard

Servono **3 terminali separati**:

**Terminale 1 — Bot di trading:**
```bash
cd /percorso/del/bot
source venv/bin/activate  # o .\venv\Scripts\Activate.ps1 su Windows
python hyperliquid_bot_executable_orders.py
```

**Terminale 2 — Server API:**
```bash
cd /percorso/del/bot
source venv/bin/activate
python api_server.py
```

**Terminale 3 — Frontend React:**
```bash
cd /percorso/del/bot/frontend
npm install    # solo la prima volta
npm run dev
```

Apri il browser su **http://localhost:3000** 🎉

### Cosa mostra la Dashboard

| Sezione | Descrizione |
|---------|-------------|
| **Header** | Stato bot (running/stopped), modalità (paper/live), ciclo corrente |
| **Stat Cards** | Saldo, PnL, margine, trade eseguiti, win rate, ciclo |
| **Drawdown Bar** | Barra visuale del drawdown corrente vs massimo consentito |
| **Grafico Candele** | Chart interattivo con candele e volume da Hyperliquid |
| **Equity Curve** | Valore del portfolio nel tempo |
| **Posizioni Aperte** | Tabella con size, entry, PnL, margine |
| **Risk Management** | Stop-loss, take-profit, trailing stop, break-even per posizione |
| **Trade History** | Storico trade con filtri, reasoning AI, stato |
| **Circuit Breakers** | Stato dei circuit breaker per le API |
| **Log Viewer** | Log recenti con filtro per livello |

### Protezione Dashboard (opzionale)

Per proteggere la dashboard con una API key:

```bash
# Nel file .env
DASHBOARD_API_KEY=una_chiave_segreta_a_tua_scelta
```

Poi nel browser, imposta la chiave:
```javascript
window.__DASHBOARD_API_KEY__ = 'una_chiave_segreta_a_tua_scelta'
```

> ⚠️ In modalità `live`, la dashboard **richiede** una API key configurata.

---

## ⚡ Passare al Trading Reale

> **⚠️ ATTENZIONE: Il trading reale usa soldi veri. Puoi perdere tutto il capitale investito. Testa SEMPRE in modalità paper prima di passare al live.**

### Passo 1: Testa in paper mode

Esegui il bot in paper mode per almeno qualche giorno. Verifica:
- Le decisioni AI sono sensate
- Il risk management funziona (SL/TP si attivano)
- Il bot non ha errori ricorrenti
- Il win rate è accettabile

### Passo 2: Modifica il file `.env`

```bash
# Cambia queste due righe:
EXECUTION_MODE=live
ENABLE_MAINNET_TRADING=true
```

### Passo 3: Riavvia il bot

```bash
# Ferma il bot corrente (Ctrl+C)
# Poi riavvia
python hyperliquid_bot_executable_orders.py --single-cycle  # test singolo ciclo live
python hyperliquid_bot_executable_orders.py                  # avvio continuo
```

### Differenze tra Paper e Live

| Aspetto | Paper | Live |
|---------|-------|------|
| Ordini | Simulati | Reali su Hyperliquid |
| Slippage | Simulato (5 bps) | Reale |
| Firma EIP-712 | Non necessaria | Richiesta |
| Verifica fill | Non necessaria | Attiva (polling) |
| Rischio | Nessuno | Perdita capitale reale |

---

## 🎛️ Gestione del Bot

### Comandi utili

```bash
# Singolo ciclo di test
python hyperliquid_bot_executable_orders.py --single-cycle

# Avvio continuo
python hyperliquid_bot_executable_orders.py

# Controlla posizioni correnti
python check_current_positions.py

# Chiudi posizione SOL manualmente
python close_sol_position.py

# Test ordine minimale
python hyperliquid_minimal_order.py

# Test connessione e configurazione
python scripts/test_connection.py
```

### File di stato

Il bot salva il suo stato in file JSON nella cartella `state/`:

| File | Contenuto |
|------|-----------|
| `state/bot_state.json` | Stato persistente: peak portfolio, trade history, equity snapshots |
| `state/bot_metrics.json` | Metriche: cicli, trade, errori, holds |
| `state/bot_live_status.json` | Stato live per la dashboard (aggiornato ogni ciclo) |
| `state/managed_positions.json` | Posizioni gestite con SL/TP/trailing/break-even |

### Log

I log sono salvati in formato JSON strutturato:

```bash
# Vedi log in tempo reale
tail -f logs/hyperliquid_bot.log

# Cerca errori
grep '"level":"ERROR"' logs/hyperliquid_bot.log

# Cerca trade eseguiti
grep '"trades_executed"' logs/hyperliquid_bot.log
```

### Shutdown sicuro

Il bot gestisce lo shutdown in modo pulito:

1. **`Ctrl+C`** — Invia SIGINT, il bot completa il ciclo corrente e salva lo stato
2. **`kill <PID>`** — Invia SIGTERM, stesso comportamento di Ctrl+C
3. **`kill -9 <PID>`** — Forza la chiusura (lo stato potrebbe non essere salvato)

> Usa sempre `Ctrl+C` o `kill` (senza `-9`) per uno shutdown pulito.

---

## 📈 Strategia di Trading

### Analisi Multi-Timeframe

Il bot analizza 3 timeframe per ogni moneta:

| Timeframe | Uso | Indicatori |
|-----------|-----|------------|
| **5 minuti** | Timing di entrata/uscita | EMA 9/20, RSI 7/14, MACD, Bollinger, VWAP, ATR |
| **1 ora** | Conferma trend | EMA 9/20, RSI 14, MACD, ATR |
| **4 ore** | Direzione macro | EMA 20/50, RSI 14, MACD, ATR |

### Criteri di Entrata

Il bot apre posizioni solo quando:
1. **Almeno 2 su 3 timeframe** concordano sulla direzione
2. **RSI** conferma (30-45 per long, 55-70 per short)
3. **Volume** sopra la media (ratio > 1.2)
4. **MACD** allineato con la direzione
5. **Bollinger** vicino alla banda appropriata
6. **VWAP** conferma (prezzo sotto per long, sopra per short)

### Gestione del Rischio

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| **Stop-Loss** | 3% | Chiude la posizione se il prezzo scende del 3% |
| **Take-Profit** | 5% | Chiude la posizione se il prezzo sale del 5% |
| **Trailing Stop** | 2% callback | Segue il prezzo e chiude se ritraccia del 2% |
| **Break-Even** | +1.5% attivazione | Sposta lo SL a entry+0.1% dopo +1.5% di profitto |
| **Max Drawdown** | 12% | Blocca nuove aperture se il drawdown supera il 12% |
| **Max Margine** | 70% | Non apre posizioni se il margine usato supera il 70% |
| **Max per Asset** | 35% | Massimo 35% del saldo su un singolo asset |
| **Correlazione** | 0.7 | Blocca posizioni correlate nella stessa direzione |
| **Emergency De-Risk** | 85% margine | Chiude la posizione peggiore se il margine supera l'85% |

### Sizing delle Posizioni

- **Leverage 3-7x** per trade ad alta confidenza (tutti i timeframe allineati)
- **Leverage 2-4x** per trade a media confidenza
- **Mai oltre 10x** di leverage
- **Sizing adattivo alla volatilità**: più volatile = posizione più piccola
- **Meme coin** (WIF, PEPE, DOGE): leverage ridotto (2-4x), confidenza minima 80%

---

## 📱 Notifiche Telegram

### Configurazione

1. Crea un bot Telegram con [@BotFather](https://t.me/BotFather)
2. Ottieni il token del bot
3. Ottieni il tuo Chat ID (usa [@userinfobot](https://t.me/userinfobot))
4. Aggiungi al `.env`:

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=il_tuo_chat_id
```

### Notifiche inviate

| Evento | Emoji | Descrizione |
|--------|-------|-------------|
| Trade eseguito | ✅/❌ | Dettagli del trade con reasoning AI |
| Stop-Loss | 🛑 | Posizione chiusa per stop-loss |
| Take-Profit | 🎯 | Posizione chiusa per take-profit |
| Trailing Stop | 📈 | Posizione chiusa per trailing stop |
| Emergency De-Risk | 🚨 | Chiusura d'emergenza per margine critico |
| Errore | 🚨 | Errori critici del bot |
| Bot avviato | 🟢 | Conferma avvio con configurazione |
| Bot fermato | 🔴 | Conferma shutdown |

---

## 📊 Monitoraggio e Metriche

### Endpoint Prometheus

Il server API espone metriche in formato Prometheus su `/metrics`:

```bash
curl http://localhost:5000/metrics
```

Metriche disponibili:
- `bot_cycles_total` — Cicli totali
- `bot_trades_executed_total` — Trade eseguiti
- `bot_balance_usd` — Saldo corrente
- `bot_margin_usage_ratio` — Uso margine
- `bot_unrealized_pnl_usd` — PnL non realizzato
- `bot_circuit_breaker_*_state` — Stato circuit breaker
- E molte altre...

### Integrazione Grafana

Puoi collegare Prometheus a Grafana per dashboard avanzate. Configura Prometheus per scrappare `http://localhost:5000/metrics` ogni 15 secondi.

### API REST

Tutti gli endpoint della dashboard sono disponibili via API:

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/health` | GET | Health check (no auth) |
| `/api/status` | GET | Stato completo del bot |
| `/api/portfolio` | GET | Portfolio corrente |
| `/api/positions` | GET | Posizioni aperte |
| `/api/managed-positions` | GET | Posizioni con SL/TP/trailing |
| `/api/trades` | GET | Storico trade |
| `/api/trades/export` | GET | Export CSV trade |
| `/api/performance` | GET | Performance summary + equity curve |
| `/api/config` | GET | Configurazione bot (no segreti) |
| `/api/logs` | GET | Log recenti (sanitizzati) |
| `/api/candles` | GET | Candele da Hyperliquid |
| `/api/orderbook` | GET | Order book L2 |
| `/metrics` | GET | Metriche Prometheus |

---

## 🔑 Variabili d'Ambiente

### Obbligatorie

| Variabile | Descrizione |
|-----------|-------------|
| `HYPERLIQUID_PRIVATE_KEY` | Chiave privata del wallet |
| `HYPERLIQUID_WALLET_ADDRESS` | Indirizzo del wallet (deve corrispondere alla chiave) |
| `OPENROUTER_API_KEY` | API key OpenRouter per Claude |

### Trading

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `EXECUTION_MODE` | `paper` | `paper` (simulato) o `live` (reale) |
| `ENABLE_MAINNET_TRADING` | `false` | Abilita ordini reali (fail-closed) |
| `TRADING_PAIRS` | 20 monete | Monete separate da virgola |
| `DEFAULT_CYCLE_SEC` | `120` | Secondi tra i cicli |
| `ENABLE_ADAPTIVE_CYCLE` | `true` | Ciclo adattivo alla volatilità |
| `MIN_CYCLE_SEC` | `30` | Ciclo minimo (alta volatilità) |
| `MAX_CYCLE_SEC` | `300` | Ciclo massimo (bassa volatilità) |
| `MAX_TRADES_PER_CYCLE` | `2` | Massimo trade per ciclo |

### Risk Management

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `DEFAULT_SL_PCT` | `0.03` | Stop-loss 3% |
| `DEFAULT_TP_PCT` | `0.05` | Take-profit 5% |
| `DEFAULT_TRAILING_CALLBACK` | `0.02` | Trailing stop callback 2% |
| `ENABLE_TRAILING_STOP` | `true` | Abilita trailing stop |
| `TRAILING_ACTIVATION_PCT` | `0.02` | Attiva trailing dopo +2% |
| `BREAK_EVEN_ACTIVATION_PCT` | `0.015` | Attiva break-even dopo +1.5% |
| `BREAK_EVEN_OFFSET_PCT` | `0.001` | Offset break-even (entry + 0.1%) |
| `HARD_MAX_LEVERAGE` | `7` | Leverage massimo assoluto |
| `MAX_MARGIN_USAGE` | `0.70` | Uso margine massimo (70%) |
| `MAX_DRAWDOWN_PCT` | `0.12` | Drawdown massimo (12%) |
| `MAX_SINGLE_ASSET_PCT` | `0.35` | Max esposizione singolo asset (35%) |
| `EMERGENCY_MARGIN_THRESHOLD` | `0.85` | Soglia emergency de-risk (85%) |
| `MAX_ORDER_MARGIN_PCT` | `0.08` | Max margine per singolo ordine (8%) |
| `DAILY_NOTIONAL_LIMIT_USD` | `500` | Limite notionale giornaliero |
| `TRADE_COOLDOWN_SEC` | `300` | Cooldown tra trade sulla stessa moneta |
| `CORRELATION_THRESHOLD` | `0.7` | Soglia correlazione per blocco |

### LLM

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `LLM_MODEL` | `anthropic/claude-opus-4` | Modello LLM |
| `LLM_MAX_TOKENS` | `8192` | Token massimi risposta |
| `LLM_TEMPERATURE` | `0.15` | Temperatura (bassa = deterministico) |

### Connessione

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `HYPERLIQUID_BASE_URL` | `https://api.hyperliquid.xyz` | URL API Hyperliquid |
| `HYPERLIQUID_INFO_TIMEOUT` | `15` | Timeout endpoint /info (secondi) |
| `HYPERLIQUID_EXCHANGE_TIMEOUT` | `30` | Timeout endpoint /exchange (secondi) |
| `META_CACHE_TTL_SEC` | `120` | Cache metadati (secondi) |

### Dashboard e Notifiche

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `DASHBOARD_API_KEY` | _(vuoto)_ | API key per proteggere la dashboard |
| `CORS_ALLOWED_ORIGINS` | `localhost:3000` | Origini CORS consentite |
| `API_SERVER_HOST` | `127.0.0.1` | Host server API |
| `API_SERVER_PORT` | `5000` | Porta server API |
| `TELEGRAM_BOT_TOKEN` | _(vuoto)_ | Token bot Telegram |
| `TELEGRAM_CHAT_ID` | _(vuoto)_ | Chat ID Telegram |

### Logging

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Livello log (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FILE` | `logs/hyperliquid_bot.log` | Percorso file log |

---

## 🧪 Test Automatici

Il progetto include test unitari per i componenti critici:

```bash
# Esegui tutti i test
python -m pytest tests/ -v

# Oppure singolarmente
python tests/test_models.py              # Modelli SL/TP/Trailing/Break-Even
python tests/test_risk_manager.py        # Risk manager e validazione ordini
python tests/test_technical_indicators.py # Indicatori tecnici (RSI, EMA, MACD)
python tests/test_decimals.py            # Utilità aritmetiche Decimal
python tests/test_state_store.py         # Persistenza stato e equity snapshots
```

### Cosa testano

| Test | Copertura |
|------|-----------|
| `test_models.py` | Stop-loss, take-profit, trailing stop, break-even, serializzazione |
| `test_risk_manager.py` | Validazione ordini, drawdown, margine, cooldown, correlazione |
| `test_technical_indicators.py` | EMA, RSI (Wilder), MACD, Bollinger, VWAP |
| `test_decimals.py` | Conversioni Decimal, sqrt, clamp, percentuali, margine |
| `test_state_store.py` | Salvataggio/caricamento stato, trade history, equity snapshots |

---

## 📁 Struttura del Progetto

```
hyperliquid/
├── hyperliquid_bot_executable_orders.py  # Entry point principale del bot
├── config/
│   └── bot_config.py                    # Configurazione centralizzata (BotConfig)
├── cycle_orchestrator.py                 # Logica ciclo di trading (7 fasi)
├── portfolio_service.py                  # Recupero stato portfolio da Hyperliquid
├── exchange_client.py                    # Client API Hyperliquid (firma EIP-712)
├── llm_engine.py                         # Claude Opus 4 via OpenRouter
├── execution_engine.py                   # Esecuzione ordini
├── risk_manager.py                       # Validazione rischio (drawdown, margine, sizing)
├── position_manager.py                   # Gestione SL/TP/trailing/break-even
├── correlation_engine.py                 # Analisi correlazione tra asset
├── technical_analyzer_simple.py          # Indicatori tecnici (RSI, EMA, MACD, BB, VWAP)
├── order_verifier.py                     # Verifica fill post-trade
├── state_store.py                        # Persistenza stato (scritture atomiche)
├── bot_live_writer.py                    # Stato live per dashboard
├── notifier.py                           # Notifiche Telegram
├── models.py                             # Modelli dati (dataclass/enum)
├── api/
│   ├── __init__.py                       # Factory Flask app
│   ├── config.py                         # Configurazione API
│   ├── auth.py                           # Autenticazione API key
│   ├── json_provider.py                  # Serializzazione Decimal → float
│   ├── helpers.py                        # Helper condivisi (proxy Hyperliquid, sanitizzazione)
│   └── routes/
│       ├── health.py                     # /api/health
│       ├── bot.py                        # /api/status, /api/portfolio, /api/config
│       ├── trading.py                    # /api/trades, /api/performance, /api/trades/export
│       ├── market.py                     # /api/candles, /api/orderbook
│       ├── logs.py                       # /api/logs
│       └── metrics.py                    # /metrics (Prometheus)
├── api_server.py                         # Entry point server API
├── utils/
│   ├── file_io.py                        # Scritture atomiche con permessi 0o600
│   ├── http.py                           # Sessione HTTP condivisa con retry
│   ├── circuit_breaker.py                # Pattern circuit breaker
│   ├── rate_limiter.py                   # Token bucket rate limiter
│   ├── retry.py                          # Retry HTTP con backoff esponenziale
│   ├── decimals.py                       # Utilità aritmetiche Decimal
│   ├── validation.py                     # Validazione input
│   ├── metrics.py                        # Raccolta metriche + export Prometheus
│   ├── health.py                         # Monitoraggio salute sistema
│   └── logging_config.py                 # Logging strutturato JSON
├── scripts/
│   └── test_connection.py                # Script test configurazione
├── tests/                                # Test unitari
├── check_current_positions.py            # Utility: controlla posizioni
├── close_sol_position.py                 # Utility: chiudi posizione SOL
├── hyperliquid_minimal_order.py          # Utility: test ordine minimale
├── requirements.txt                      # Dipendenze Python
├── .env.example                          # Template variabili d'ambiente
└── state/                                # Stato runtime (auto-creato)
    ├── bot_state.json
    ├── bot_metrics.json
    ├── bot_live_status.json
    └── managed_positions.json
```

---

## 🏗️ Architettura

```
┌─────────────────────────────────────────────────────────┐
│                    Dashboard React                       │
│  (Grafico Candele, Order Book, Posizioni, Trade, Log)   │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP (polling ogni 5s)
┌──────────────────────▼──────────────────────────────────┐
│              Server API (Flask Blueprints)                │
│  routes: health, bot, trading, market, logs, metrics     │
└──────────────────────┬──────────────────────────────────┘
                       │ Legge file JSON condivisi
┌──────────────────────▼──────────────────────────────────┐
│              Processo Bot                                 │
│                                                           │
│  BotConfig ──→ HyperliquidBot ──→ CycleOrchestrator     │
│                                                           │
│  7 Fasi per ciclo:                                        │
│    1. Health check (ogni 10 cicli)                       │
│    2. Snapshot portfolio (PortfolioService)               │
│    3. SL/TP/Trailing/Break-even (PositionManager)        │
│    4. Emergency de-risk (RiskManager)                    │
│    5. Analisi correlazione (CorrelationEngine)           │
│    6. Per-moneta: tecnici → LLM → rischio → esecuzione  │
│    7. Persistenza stato (StateStore)                     │
└──────────────────────────────────────────────────────────┘
```

### Flusso di un ciclo di trading

```
Inizio Ciclo
    │
    ├─→ Health Check (connettività, disco, permessi)
    │
    ├─→ Recupera Portfolio (saldo, posizioni, margine)
    │
    ├─→ Registra Equity Snapshot (per grafico equity)
    │
    ├─→ Controlla SL/TP/Trailing/Break-Even
    │   └─→ Se attivato → Chiudi posizione → Notifica
    │
    ├─→ Emergency De-Risk (se margine > 85%)
    │   └─→ Chiudi posizione peggiore
    │
    ├─→ Calcola Correlazioni tra asset
    │
    ├─→ Per ogni moneta:
    │   ├─→ Recupera indicatori tecnici (5m, 1h, 4h)
    │   ├─→ Recupera funding rate e open interest
    │   ├─→ Invia tutto a Claude Opus 4
    │   ├─→ Ricevi decisione (buy/sell/hold/close/...)
    │   ├─→ Controlla correlazione
    │   ├─→ Valida con Risk Manager
    │   ├─→ Esegui ordine (paper o live)
    │   ├─→ Verifica fill (solo live)
    │   ├─→ Registra posizione gestita (SL/TP)
    │   └─→ Notifica Telegram
    │
    ├─→ Salva stato su disco
    │
    └─→ Calcola prossimo ciclo (adattivo)
```

---

## 🔧 Risoluzione Problemi

### Il bot non si avvia

```
CRITICAL: HYPERLIQUID_WALLET_ADDRESS not set
```
→ Controlla che il file `.env` esista e contenga `HYPERLIQUID_WALLET_ADDRESS`

```
CRITICAL: HYPERLIQUID_WALLET_ADDRESS does not match the address derived from HYPERLIQUID_PRIVATE_KEY
```
→ La chiave privata e l'indirizzo wallet non corrispondono. Verifica entrambi nel `.env`

### Errori di connessione

```
Circuit breaker OPEN for /info endpoint
```
→ L'API Hyperliquid non risponde. Attendi 30-60 secondi, il circuit breaker si riproverà automaticamente

```
OpenRouter timeout after all retries
```
→ OpenRouter è lento o non raggiungibile. Il bot userà il fallback "hold" e riproverà al prossimo ciclo

### Ordini rifiutati

```
Exchange rejected order: insufficient margin
```
→ Non hai abbastanza margine disponibile. Riduci il leverage o chiudi posizioni esistenti

```
risk rejected: cooldown_active
```
→ Il cooldown tra trade sulla stessa moneta non è ancora scaduto (default: 5 minuti)

```
risk rejected: daily_notional_cap_exceeded
```
→ Hai raggiunto il limite notionale giornaliero. Attendi il giorno successivo o aumenta `DAILY_NOTIONAL_LIMIT_USD`

### La dashboard non si connette

```
API Server Not Running
```
→ Assicurati che `python api_server.py` sia in esecuzione nel terminale 2

→ Verifica che la porta 5000 non sia occupata: `lsof -i :5000` (Linux/macOS) o `netstat -ano | findstr :5000` (Windows)

### Il grafico candele non carica

→ Il frontend prova prima il proxy API (porta 5000), poi direttamente Hyperliquid. Se nessuno dei due funziona, controlla la connessione internet.

---

## 💰 Costi Stimati

| Componente | Costo |
|-----------|-------|
| **OpenRouter (Claude Opus 4)** | ~$0.03 per chiamata LLM |
| **5 monete, ciclo 2 min** | ~$2-4/giorno |
| **20 monete, ciclo 2 min** | ~$8-15/giorno |
| **5 monete, ciclo 15 min** | ~$0.50-1/giorno |
| **Hyperliquid** | Nessun costo API, solo commissioni trading |
| **Server** | Qualsiasi VPS da $5/mese o il tuo PC |

> 💡 **Consiglio**: Inizia con poche monete (3-5) e ciclo lungo (5-15 min) per contenere i costi. Aumenta gradualmente.

Per ridurre i costi:
- Riduci il numero di `TRADING_PAIRS`
- Aumenta `DEFAULT_CYCLE_SEC` (es. 300 = 5 minuti)
- Disabilita `ENABLE_ADAPTIVE_CYCLE` (il ciclo adattivo può accelerare in alta volatilità)

---

## 🔒 Sicurezza

### Protezioni implementate

| Protezione | Dettaglio |
|-----------|-----------|
| **Chiave privata** | Mai salvata come attributo — solo l'oggetto `Account` derivato |
| **API key OpenRouter** | Solo negli header della sessione HTTP, mai nei log |
| **Token Telegram** | Costruito nell'URL solo al momento dell'invio |
| **File di stato** | Permessi `0o600` (solo proprietario) |
| **Scritture atomiche** | Pattern write-to-temp-then-rename per evitare corruzione |
| **Log sanitizzati** | Chiavi private, token e API key redatti prima di servire alla dashboard |
| **Validazione wallet** | Indirizzo verificato contro la chiave privata all'avvio |
| **CORS** | Origini validate, wildcard vietato in modalità live |
| **Dashboard auth** | API key obbligatoria in modalità live |
| **Fail-closed** | `ENABLE_MAINNET_TRADING` deve essere esplicitamente `true` per ordini reali |

### Raccomandazioni

1. **Non esporre** il server API su internet senza un reverse proxy con TLS
2. **Usa sempre** `DASHBOARD_API_KEY` in produzione
3. **Non committare** mai il file `.env` nel repository
4. **Usa un wallet dedicato** solo per il bot, con fondi limitati
5. **Monitora** regolarmente i log e le notifiche Telegram

---

## ⚠️ Disclaimer

**Questo software è fornito "così com'è" senza alcuna garanzia, espressa o implicita.**

- Il trading di criptovalute è **altamente rischioso** e può risultare nella **perdita totale** dei fondi investiti
- Le performance passate **non garantiscono** risultati futuri
- Le decisioni dell'AI **non sono infallibili** e possono portare a perdite
- L'autore **non è responsabile** per eventuali perdite finanziarie derivanti dall'uso di questo software
- **Testa sempre** in modalità paper prima di usare soldi reali
- **Non investire** mai più di quanto puoi permetterti di perdere
- Questo software **non costituisce** consulenza finanziaria

**Usalo a tuo rischio e pericolo.**