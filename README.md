# Bot Trading Hyperliquid

Un bot di trading automatizzato per l'exchange Hyperliquid, alimentato da **Claude Opus 4.6** via OpenRouter per decisioni di trading intelligenti. Tutti i dati di mercato sono **sorgenti esclusivamente dall'API Hyperliquid** — nessuna fonte dati esterna.

## 🚀 Caratteristiche

### ✅ Funzionalità Core
- **Trading Potenziato AI**: Claude Opus 4.6 (`anthropic/claude-opus-4.6`) via OpenRouter analizza dati di mercato e genera decisioni di trading eseguibili
- **Dati Solo Hyperliquid**: Tutti i dati di mercato (candele, prezzi mid, tassi funding, interesse aperto) sorgenti direttamente dall'API Hyperliquid
- **Analisi Tecnica**: EMA, MACD, RSI (Wilder's), ATR, Bande di Bollinger, VWAP calcolati da snapshot candele Hyperliquid
- **Multi-Timeframe**: Analisi su 5m (intraday), 1h (medium), 4h (long-term) con rilevamento allineamento trend
- **Gestione Rischio**: Dimensionamento basato su volatilità, limiti margine, cooldown trade, limiti notionale giornaliero, protezione drawdown massimo
- **Esecuzione Sicura**: Ordini firmati EIP-712 via `eth_account` per mainnet Hyperliquid
- **Modalità Paper Trading**: Test sicuri con esecuzioni simulate e slippage
- **Circuit Breaker**: Gestione fallimenti automatica per endpoint API
- **Rate Limiter**: Token bucket per API Hyperliquid e OpenRouter
- **Health Monitor**: Controlli salute periodici (exchange, disco, stato)
- **Dashboard in Tempo Reale**: Frontend React con portfolio live, posizioni, storia trade, e log
- **Logging Strutturato**: Log in formato JSON per monitoraggio e debug
- **Metriche Prometheus**: Endpoint `/metrics` per integrazione Grafana

### 📊 Dashboard
Il bot include una **dashboard web in tempo reale** costruita con React + Tailwind CSS:
- 💰 Saldo portfolio live e PnL
- 📈 **Vera equity curve** (valore portfolio nel tempo, non solo trade)
- 📊 Posizioni aperte con prezzi entrata e PnL non realizzato
- 🛡️ **Gestione rischio visuale**: SL/TP/Trailing/Break-Even per ogni posizione
- 📋 Storia trade completa con ragionamento AI e filtri
- 🔄 Stato circuit breaker
- 📝 Visualizzatore log in tempo reale con filtri livello
- 📉 Barra drawdown con limiti visuali
- ⬇️ Export CSV storia trade
- 💥 ErrorBoundary per crash recovery

### 🛡️ Gestione Posizioni
| Feature | Descrizione |
|---------|-------------|
| **Stop-Loss** | 3% predefinito, configurabile per posizione |
| **Take-Profit** | 5% predefinito, configurabile per posizione |
| **Trailing Stop** | 2% callback, attivazione dopo +2% profitto |
| **Break-Even** | Sposta SL a entry+0.1% dopo +1.5% profitto |
| **Emergency De-Risk** | Chiude posizione peggiore se margine > 88% |

### 📊 Asset Supportati
| Asset | Dimensione Minima | Valore Appross. |
|-------|-------------------|-----------------|
| BTC   | 0.001             | ~$111           |
| ETH   | 0.01              | ~$40            |
| SOL   | 0.1               | ~$19            |
| BNB   | 0.01              | ~$7             |
| ADA   | 10.0              | ~$6.50          |
| + 15 altri | Dinamico     | Calcolato       |

### 🛡️ Caratteristiche Sicurezza
- **Protezione Drawdown Massimo**: Ferma aperture nuove posizioni se drawdown supera 15%
- **De-Risk di Emergenza**: Chiude automaticamente posizione peggiore se uso margine > 88%
- **Rilevamento Conflitto Posizione**: Previene apertura direzione opposta su stesso asset
- **Limite Concentrazione Per-Asset**: Max 40% del saldo su singolo asset
- **Correlazione Asset**: Previene apertura posizioni correlate nella stessa direzione
- **Fallback Sicuro**: Hold/de-risk automatico quando AI non disponibile
- **Circuit Breaker**: Previene cascate fallimenti da outage API
- **Rate Limiter**: Token bucket per prevenire throttling API
- **Shutdown Graceful**: Handler SIGINT/SIGTERM salvano stato prima dell'uscita
- **Validazione Config**: Controlla variabili critiche all'avvio

## 📋 Requisiti

- Python 3.10+
- Node.js 18+ (per dashboard)
- Wallet Hyperliquid valido con chiave privata
- Chiave API OpenRouter (per accesso Claude Opus 4.6)

## 🛠️ Installazione

1. **Clona il repository**:
   ```bash
   git clone <repository-url>
   cd hyperliquid-trading-bot
   ```

2. **Installa dipendenze Python**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Installa dipendenze Dashboard**:
   ```bash
   cd frontend
   npm install
   cd ..
   ```

4. **Configura ambiente**:
   ```bash
   cp .env.example .env
   # Modifica .env con le tue chiavi API e impostazioni
   ```

## 🚀 Uso

### Avvia il Bot
```bash
# Ciclo singolo test
python hyperliquid_bot_executable_orders.py --single-cycle

# Trading continuo
python hyperliquid_bot_executable_orders.py
```

### Avvia la Dashboard
```bash
# Terminale 1: Avvia server API
python api_server.py

# Terminale 2: Avvia frontend
cd frontend
npm run dev
```

Poi apri **http://localhost:3000** nel browser.

### Prometheus Metrics
Metriche disponibili su `http://localhost:5000/metrics` in formato testo Prometheus.

## ⚙️ Configurazione

### Variabili Ambiente (.env)

```bash
# === RICHIESTE ===
HYPERLIQUID_PRIVATE_KEY=la_tua_private_key_qui
HYPERLIQUID_WALLET_ADDRESS=il_tuo_wallet_address_qui
OPENROUTER_API_KEY=la_tua_api_key_openrouter_qui

# === Modalità Esecuzione ===
EXECUTION_MODE=paper
ENABLE_MAINNET_TRADING=false

# === Impostazioni AI / LLM ===
LLM_MODEL=anthropic/claude-opus-4.6
LLM_MAX_TOKENS=8192
LLM_TEMPERATURE=0.15

# === Gestione Rischio ===
MAX_ORDER_MARGIN_PCT=0.1
HARD_MAX_LEVERAGE=10
MAX_MARGIN_USAGE=0.8
MAX_DRAWDOWN_PCT=0.15
TRADE_COOLDOWN_SEC=300
DAILY_NOTIONAL_LIMIT_USD=1000

# === Stop-Loss / Take-Profit / Trailing / Break-Even ===
DEFAULT_SL_PCT=0.03
DEFAULT_TP_PCT=0.05
ENABLE_TRAILING_STOP=true
DEFAULT_TRAILING_CALLBACK=0.02
BREAK_EVEN_ACTIVATION_PCT=0.015
BREAK_EVEN_OFFSET_PCT=0.001

# === Ciclo Adattivo ===
ENABLE_ADAPTIVE_CYCLE=true
DEFAULT_CYCLE_SEC=60

# === Server API ===
API_SERVER_PORT=5000
```

## 🔄 Architettura

```
┌─────────────────────────────────────────────────────────┐
│                    Dashboard React                       │
│  (Portfolio, Equity Curve, Posizioni, Trade, Log, BE)   │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP (polling ogni 5s)
┌──────────────────────▼──────────────────────────────────┐
│              Server API Flask + Prometheus                │
│  /api/status  /api/portfolio  /api/trades  /metrics      │
└──────────────────────┬──────────────────────────────────┘
                       │ Legge file JSON condivisi
┌──────────────────────▼──────────────────────────────────┐
│              Processo Bot Trading Principale             │
│                                                           │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐              │
│  │Exchange  │  │ LLM      │  │ Risk       │              │
│  │Client    │  │ Engine   │  │ Manager    │              │
│  │(HL API)  │  │(Claude)  │  │            │              │
│  └────┬─────┘  └────┬─────┘  └─────┬──────┘              │
│       │              │              │                     │
│  ┌────▼──────────────▼──────────────▼──────┐             │
│  │         Execution Engine                 │             │
│  └────────────────┬────────────────────────┘             │
│                   │                                       │
│  ┌────────────────▼────────────────────────┐             │
│  │  Position Manager (SL/TP/Trail/BE)      │             │
│  └────────────────┬────────────────────────┘             │
│                   │                                       │
│  ┌────────────────▼────────────────────────┐             │
│  │  State Store + Equity Snapshots          │             │
│  └──────────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────┘
```

## ⚠️ Disclaimer

Questo software è fornito come-è senza garanzia. Il trading di criptovalute è altamente rischioso e può risultare in perdita totale di fondi. Testa sempre accuratamente in modalità paper e non rischiare mai più di quanto puoi permetterti di perdere.