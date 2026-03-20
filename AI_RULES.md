# Regole AI per Bot Trading Hyperliquid

## Stack Tecnologico
- **Python 3.10+**: Linguaggio core per il bot, sfruttando type hints (`typing`), dataclasses, e enums per codice strutturato.
- **requests**: Client HTTP primario per tutte le interazioni API (Hyperliquid, OpenRouter).
- **eth_account**: Gestisce firma EIP-712 per ordini Hyperliquid usando `Account.from_key()` e `encode_typed_data`.
- **pycryptodome (Crypto.Hash.keccak)**: Hashing Keccak-256 per firme azioni Hyperliquid.
- **msgpack**: Serializzazione binaria per payload Hyperliquid (`msgpack.packb`).
- **decimal.Decimal**: Aritmetica precisa per tutti i calcoli finanziari (prezzi, dimensioni, margini, PnL).
- **python-dotenv**: Caricamento variabili d'ambiente per segreti (chiavi private, API keys).
- **logging**: Modulo built-in per logging strutturato JSON su file e console.

## Configurazione LLM
- **Modello**: `anthropic/claude-opus-4.6` via OpenRouter (`https://openrouter.ai/api/v1`)
- **Chiave API**: Variabile d'ambiente `OPENROUTER_API_KEY`
- **Timeout**: 90 secondi (Claude Opus 4.6 può richiedere più tempo rispetto a modelli più piccoli)
- **Retry**: 2 retry su 429/500/502/503/504 con backoff esponenziale
- **Temperatura**: 0.2 (bassa per decisioni di trading deterministiche)

## Fonti Dati
- **TUTTI i dati di mercato provengono esclusivamente dall'API Hyperliquid**
- Nessun Binance, CoinGecko, o altre fonti dati esterne
- Snapshot candele, prezzi mid, tassi funding, interesse aperto — tutti da Hyperliquid `/info`
- Indicatori tecnici (EMA, MACD, RSI, ATR, Bande di Bollinger) calcolati da candele Hyperliquid

## Strategia Trend 4H/1D
- **Timeframe Primario**: 4H per identificazione trend principale
- **Timeframe Secondario**: 1D per conferma trend a lungo termine
- **Timeframe Entrata**: 1H per timing preciso di entrata
- **Criteri Entrata**: EMA9 > EMA21 > EMA50 su 4H, conferma 1D, pullback su 1H
- **Volume**: Ratio > 1.5 per conferma breakout/breakdown
- **RSI**: 30-40 per long, 60-70 per short su pullback
- **SL/TP**: 5%/10% (R:R 1:2), Break-even @ +3%, Trailing @ +5%
- **Max Posizioni**: 2 posizioni trend simultanee
- **Size**: 3% portfolio per posizione trend

## Regole Uso Librerie
Segui queste regole rigorosamente per evitare errori di precisione, incompatibilità API, e problemi di sicurezza:

### HTTP & Client API
- **Usa `requests` esclusivamente** per tutte le chiamate HTTP sincrone (Hyperliquid `/info`, `/exchange`, completamenti OpenRouter). Mai usare `urllib`, `aiohttp`, o `httpx`.
- Imposta `timeout=15-90s` su tutte le richieste. Usa sempre `json=payload` per POST e gestisci `response.json()` con controlli status.
- Per Hyperliquid: Usa header `Content-Type: application/json` solo; firma payload con EIP-712 via `eth_account`.

### Crypto & Firma
- **Firma EIP-712: `eth_account` solo**. Usa `Account.from_key(private_key)` e pattern `sign_l1_action_exact` da `exchange_client.py`. Mai implementare firma manuale.
- **Hashing: `Crypto.Hash.keccak` esclusivamente** per hash azioni. Importa come `from Crypto.Hash import keccak`.
- **Msgpack: Usa `msgpack.packb`** per dati azione Hyperliquid prima dell'hashing. Mai usare JSON per payload firmati.

### Precisione Finanziaria
- **Tutti i soldi/matematica: `decimal.Decimal(str(value))`**. Converti float/JSON a Decimal immediatamente. Mai usare `float` per prezzi, dimensioni, margini, o PnL.
- Arrotonda prezzi a tick sizes dinamicamente via `get_tick_size_and_precision`. Usa `max_leverage` da API `/meta`.

### Configurazione & Segreti
- **Var ambiente: `dotenv.load_dotenv()` all'inizio modulo**. Accedi via `os.getenv('KEY')`. Documenta in `.env.example`.
- Aggiorna `requirements.txt` per nuove lib.

### Dati & Logging
- **Dati strutturati: `dataclass` e `Dict[str, Any]`**. Usa `Enum` per azioni (es. `TradingAction`).
- **Logging: formato JSON strutturato** con handler file+console. Usa `logger.info/error` a livello INFO. Nessun `print` per logica produzione.
- **Parsing JSON: `json.loads` con estrazione regex se risposte LLM sono disordinate**. Valida schemi prima dell'esecuzione.

### Gestione Stato
- **Scritture atomiche**: File stato usano pattern write-to-temp-then-rename per evitare corruzione.
- **Tracking notionale giornaliero**: Usa chiavi per-giorno con pulizia automatica 7 giorni.
- **Shutdown graceful**: Handler segnali (SIGINT/SIGTERM) salvano stato prima dell'uscita.

### Circuit Breaker
- **OPEN -> HALF_OPEN transizione**: Basata su `recovery_timeout` trascorso.
- **HALF_OPEN -> CLOSED**: Alla prima chiamata riuscita.
- **HALF_OPEN -> OPEN**: Al fallimento durante half-open.

### Proibizioni
- Nessun codice async (`asyncio`, `aiohttp`) a meno che non richiesto esplicitamente.
- Nessuna nuova lib ML/dati (es. pandas, numpy) – mantieni leggero.
- Nessun float in logica trading – causa rifiuti Hyperliquid.
- Nessuna fonte dati esterna (Binance, CoinGecko, ecc.) – solo Hyperliquid.
- Testa tutti i cambiamenti con `--single-cycle` prima di run continui.

**Applicato da AI Editor**: Tutti i futuri cambiamenti devono seguire queste regole. Violazioni saranno rifiutate.