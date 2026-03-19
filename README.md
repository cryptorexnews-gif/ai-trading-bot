# Bot Trading Hyperliquid

Un bot di trading automatizzato per l'exchange Hyperliquid, alimentato da **Claude Opus 4.6** via OpenRouter per decisioni di trading intelligenti. Tutti i dati di mercato sono **sorgenti esclusivamente dall'API Hyperliquid** — nessuna fonte dati esterna.

## 🚀 Caratteristiche

### ✅ Funzionalità Core
- **Trading Potenziato AI**: Claude Opus 4.6 (`anthropic/claude-opus-4.6`) via OpenRouter analizza dati di mercato e genera decisioni di trading eseguibili
- **Dati Solo Hyperliquid**: Tutti i dati di mercato (candele, prezzi mid, tassi funding, interesse aperto) sorgenti direttamente dall'API Hyperliquid
- **Analisi Tecnica**: EMA, MACD, RSI, ATR, Bande di Bollinger, VWAP calcolati da snapshot candele Hyperliquid
- **Gestione Rischio**: Dimensionamento basato su volatilità, limiti margine, cooldown trade, limiti notionale giornaliero, protezione drawdown massimo
- **Esecuzione Sicura**: Ordini firmati EIP-712 via `eth_account` per mainnet Hyperliquid
- **Modalità Paper Trading**: Test sicuri con esecuzioni simulate e slippage
- **Circuit Breaker**: Gestione fallimenti automatica per endpoint API
- **Dashboard in Tempo Reale**: Frontend React con portfolio live, posizioni, storia trade, e log
- **Logging Strutturato**: Log in formato JSON per monitoraggio e debug

### 📊 Dashboard
Il bot include una **dashboard web in tempo reale** costruita con React + Tailwind CSS:
- 💰 Saldo portfolio live e PnL
- 📈 Grafico timeline attività
- 📊 Posizioni aperte con prezzi entrata e PnL non realizzato
- 📋 Storia trade completa con ragionamento AI
- 🛡️ Stato circuit breaker
- 📝 Visualizzatore log in tempo reale
- ⚠️ Avvisi rischio (perdite consecutive, cicli falliti)

### 📊 Asset Supportati
| Asset | Dimensione Minima | Valore Appross. |
|-------|-------------------|-----------------|
| BTC   | 0.001             | ~$111           |
| ETH   | 0.001             | ~$4             |
| SOL   | 0.1               | ~$19            |
| BNB   | 0.001             | ~$1             |
| ADA   | 16.0              | ~$10.50         |

### 🛡️ Caratteristiche Sicurezza
- **Protezione Drawdown Massimo**: Ferma aperture nuove posizioni se drawdown supera 15%
- **De-Risk di Emergenza**: Chiude automaticamente posizione peggiore se uso margine > 90%
- **Rilevamento Conflitto Posizione**: Previene apertura direzione opposta su stesso asset
- **Limite Concentrazione Per-Asset**: Max 40% del saldo su singolo asset
- **Fallback Sicuro**: Hold/de-risk automatico quando AI non disponibile
- **Circuit Breaker**: Previene cascate fallimenti da outage API
- **Shutdown Graceful**: Handler SIGINT/SIGTERM salvano stato prima dell'uscita

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

### Avvia Tutto Insieme
```bash
# Terminale 1: Bot
python hyperliquid_bot_executable_orders.py

# Terminale 2: API + Dashboard
python api_server.py &
cd frontend && npm run dev
```

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
LLM_TEMPERATURE=0.2

# === Gestione Rischio ===
MAX_ORDER_MARGIN_PCT=0.1
HARD_MAX_LEVERAGE=10
MAX_MARGIN_USAGE=0.8
MAX_DRAWDOWN_PCT=0.15
TRADE_COOLDOWN_SEC=300
DAILY_NOTIONAL_LIMIT_USD=1000

# === Server API ===
API_SERVER_PORT=5000
```

## 🔄 Architettura

```
┌─────────────────────────────────────────────────────────┐
│                    Dashboard React                       │
│  (Portfolio, Posizioni, Trade, Log, Circuit Breaker)    │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP (polling ogni 5s)
┌──────────────────────▼──────────────────────────────────┐
│                  Server API Flask                        │
│  /api/status  /api/portfolio  /api/trades  /api/logs     │
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
│  │    State Store (JSON) + Live Writer      │             │
│  └──────────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────┘
```

## ⚠️ Disclaimer

Questo software è fornito come-è senza garanzia. Il trading di criptovalute è altamente rischioso e può risultare in perdita totale di fondi. Testa sempre accuratamente in modalità paper e non rischiare mai più di quanto puoi permetterti di perdere.