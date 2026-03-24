# Hyperliquid AI Trading Bot — Documentazione Completa

Bot di trading automatico per Hyperliquid con:
- motore decisionale LLM (DeepSeek via OpenRouter),
- gestione rischio avanzata (SL/TP/trailing/break-even),
- dashboard React in tempo reale,
- API Flask modulari,
- modalità di firma **esclusiva con API wallet signer** (master wallet non esposto).

---

## Indice

1. [Panoramica progetto](#panoramica-progetto)  
2. [Caratteristiche principali](#caratteristiche-principali)  
3. [Architettura tecnica](#architettura-tecnica)  
4. [Modalità sicurezza: API wallet signer (obbligatoria)](#modalità-sicurezza-api-wallet-signer-obbligatoria)  
5. [Stack tecnologico](#stack-tecnologico)  
6. [Struttura repository](#struttura-repository)  
7. [Configurazione ambiente (.env)](#configurazione-ambiente-env)  
8. [Tutorial sviluppo passo passo](#tutorial-sviluppo-passo-passo)  
9. [Comandi operativi di setup (Dyad)](#comandi-operativi-di-setup-dyad)  
10. [Deploy produzione: Frontend Vercel + Backend VPS](#deploy-produzione-frontend-vercel--backend-vps)  
11. [Dashboard: sezioni e uso operativo](#dashboard-sezioni-e-uso-operativo)  
12. [Risk management e strategia](#risk-management-e-strategia)  
13. [API principali](#api-principali)  
14. [Troubleshooting](#troubleshooting)  
15. [Best practice operative](#best-practice-operative)

---

## Panoramica progetto

Questo progetto è un trading bot che opera su Hyperliquid e include un’interfaccia dashboard per monitoraggio e controllo runtime.

### Obiettivi del sistema
- Eseguire cicli di analisi continui su più asset.
- Decidere azioni di trading tramite LLM su dati Hyperliquid.
- Applicare gestione posizione automatica (SL/TP/trailing/break-even).
- Esporre API e metriche per osservabilità e controllo.
- Separare frontend e backend per deploy production-ready.

---

## Caratteristiche principali

- **Dati di mercato solo Hyperliquid** (`/info`, `/exchange`).
- **Decision engine LLM** con validazione output JSON.
- **Strategie runtime**: trend e scalping.
- **Gestione ordini protettivi** con sincronizzazione su exchange.
- **Circuit breaker e rate limiter** per resilienza.
- **Persistenza stato atomica** (state/metrics/trade history/equity snapshots).
- **Dashboard real-time** (overview, settings, positions, history, system).
- **Modalità firma sicura**: API wallet signer dedicato.
- **Deploy consigliato**: frontend su Vercel, backend su VPS con reverse proxy TLS.

---

## Architettura tecnica

### Moduli principali
- `hyperliquid_bot_executable_orders.py`: entrypoint bot.
- `bot/`: lifecycle, cycle execution, runtime config application.
- `cycle_orchestrator.py`: orchestrazione fasi ciclo.
- `exchange_client.py` + `exchange/`: client Hyperliquid, firma EIP-712, ordini.
- `llm_engine.py` + `llm/prompt_builder.py`: decisioni LLM.
- `risk_manager.py`, `position_manager.py`: risk & position controls.
- `api/`: server Flask modulare (route + service layer).
- `src/`: frontend React/Vite dashboard.
- `state_store.py`: stato persistente e metriche.
- `utils/`: circuit breaker, retry, validazioni, indicatori, logging.

### Flusso semplificato
1. Bot legge config runtime e stato.
2. Recupera portfolio + dati mercato Hyperliquid.
3. Calcola indicatori multi-timeframe.
4. Chiede decisione al LLM.
5. Applica controlli rischio.
6. Esegue ordine e verifica fill.
7. Sincronizza ordini protettivi.
8. Aggiorna stato e dashboard.

---

## Modalità sicurezza: API wallet signer (obbligatoria)

Il progetto è configurato per usare **solo** signer delegato (`api_wallet`), così il wallet master non espone mai la sua private key.

### Modello operativo
- `HYPERLIQUID_WALLET_ADDRESS` = wallet master (trading account).
- `HYPERLIQUID_API_SIGNER_PRIVATE_KEY` = chiave signer delegato.
- `HYPERLIQUID_SIGNER_MODE=api_wallet`.
- I payload firmati includono `vaultAddress` del wallet master.

### Implicazioni
- Se il signer mode non è `api_wallet`, il bot si blocca.
- Se è presente una key legacy `HYPERLIQUID_PRIVATE_KEY`, il bot si blocca.
- Signer e master non devono coincidere.

---

## Stack tecnologico

### Backend
- Python 3.10+
- Flask + Flask-CORS + Flask-Sock
- requests
- eth_account
- msgpack
- pycryptodome (keccak)
- decimal.Decimal
- dotenv
- logging

### Frontend
- React
- Vite
- Tailwind CSS
- Recharts
- Lightweight Charts
- React Router

---

## Struttura repository

- `api/`: API server e route modulari
- `bot/`: runtime loop e servizi ciclo
- `exchange/`: firma/transazioni/order services
- `orchestration/`: decision, risk gate, execution flow
- `utils/`: helper infrastrutturali
- `src/`: dashboard frontend
- `deploy/`: config deploy (Nginx, guide VPS/Vercel)
- `state/`: file runtime persistenti

---

## Configurazione ambiente (.env)

Il file `.env` deve includere almeno:

### Identità trading
- `HYPERLIQUID_WALLET_ADDRESS`
- `HYPERLIQUID_SIGNER_MODE=api_wallet`
- `HYPERLIQUID_API_SIGNER_PRIVATE_KEY`

### Modalità esecuzione
- `EXECUTION_MODE=live`
- `ENABLE_MAINNET_TRADING=true`

### LLM
- `OPENROUTER_API_KEY`
- `LLM_MODEL=deepseek/deepseek-v3.2`

### Sicurezza dashboard
- `DASHBOARD_API_KEY` (admin)
- `DASHBOARD_READ_API_KEY` (read-only frontend)

### API/CORS
- `API_HOST`
- `API_PORT`
- `CORS_ALLOWED_ORIGINS`
- `ALLOW_LOCALHOST_BYPASS=false`

---

## Tutorial sviluppo passo passo

> Questo percorso è pensato per l’ambiente Dyad (consigliato).

### Step 1 — Preparazione config
1. Inserisci/aggiorna il `.env` con i valori reali.
2. Verifica che il signer mode sia `api_wallet`.
3. Verifica che la key legacy master non sia presente.

### Step 2 — Build ambiente
1. Usa **Rebuild** nella UI Dyad (pulsante azione).
2. Attendi installazione dipendenze backend/frontend.

### Step 3 — Avvio servizi
1. Usa **Restart** per riavviare stack applicativo.
2. Usa **Refresh** per aggiornare la preview dashboard.

### Step 4 — Verifica stato API
Controlla:
- health endpoint disponibile,
- dashboard raggiungibile,
- nessun errore auth nei log.

### Step 5 — Verifica wallet signer
Controlla nei log:
- signer mode `api_wallet`,
- trading user (master) valorizzato,
- assenza errori “wallet does not exist”.

### Step 6 — Test ciclo controllato
Esegui un ciclo singolo in modalità di test operativo interno (senza run continuo) per validare:
- fetch dati,
- decisione LLM,
- risk checks,
- sync ordini protettivi.

### Step 7 — Runtime controls
Da dashboard:
- apri **Settings**,
- configura strategia e coppie,
- salva runtime config,
- avvia/ferma bot dal pannello controllo processo.

### Step 8 — Monitoraggio sviluppo
Osserva:
- tab **Overview** (saldo, PnL, ciclo),
- tab **Positions** (posizioni/SL/TP),
- tab **System** (log, circuit breaker).

---

## Comandi operativi di setup (Dyad)

Nel workspace Dyad usa i pulsanti sopra la chat:

### 1) Rebuild
Quando usarlo:
- primo setup del progetto,
- dopo cambio dipendenze,
- se l’ambiente è incoerente.

Effetto:
- ricrea l’ambiente da zero (reinstall completa).

### 2) Restart
Quando usarlo:
- dopo modifica `.env`,
- dopo cambi backend Python,
- dopo cambi logica bot/API.

Effetto:
- riavvia i processi applicativi.

### 3) Refresh
Quando usarlo:
- dopo modifiche frontend,
- dopo restart per aggiornare la preview.

Effetto:
- aggiorna solo la pagina di anteprima.

### Sequenza consigliata di setup iniziale
1. **Rebuild**
2. **Restart**
3. **Refresh**

### Sequenza consigliata dopo modifica configurazione (.env)
1. **Restart**
2. **Refresh**

---

## Deploy produzione: Frontend Vercel + Backend VPS

### Obiettivo
- Frontend pubblico su Vercel.
- Backend Flask/Bot su VPS dietro Nginx HTTPS.

### Backend VPS
- API su `127.0.0.1:5000`.
- Reverse proxy TLS (`deploy/nginx/vps-api.conf`).
- CORS limitato ai domini frontend reali.
- Bypass localhost disabilitato.

### Frontend Vercel
Imposta environment variables:
- `VITE_API_BASE_URL=https://api.tuodominio.com/api`
- `VITE_DASHBOARD_TOKEN=<DASHBOARD_READ_API_KEY>`

### Token policy
- **Admin key**: solo backend/operazioni sensibili.
- **Read key**: solo frontend pubblico.

### Opzionale hardening
- `ADMIN_ALLOWED_IPS` per limitare endpoint admin.
- Rotazione periodica token.

---

## Dashboard: sezioni e uso operativo

### Overview
- Bilancio, margine, PnL, ciclo bot, chart mercato.

### Settings
- Start/Stop processo bot.
- Config runtime strategia, parametri, coppie.

### Positions
- Posizioni aperte, SL/TP/trailing/break-even.

### History
- Trade recenti, equity curve, export CSV.

### System
- Log live, stato circuit breaker, diagnostica.

---

## Risk management e strategia

### Risk controls principali
- max drawdown,
- max margin usage,
- trade cooldown,
- notional giornaliero,
- max leva.

### Strategia trend
- allineamento multi-timeframe,
- gestione posizione conservativa,
- protezioni obbligatorie.

### Strategia scalping
- focus timeframe 5m,
- conferma momentum/volume,
- gestione rischio dinamica.

---

## API principali

- `GET /api/health`
- `GET /api/status`
- `GET /api/portfolio`
- `GET /api/positions`
- `GET /api/managed-positions`
- `GET /api/runtime-config`
- `POST /api/runtime-config`
- `GET /api/trades`
- `GET /api/performance`
- `GET /api/logs`
- `GET /metrics`

---

## Troubleshooting

### 1) Unauthorized dashboard
- verifica `X-API-Key`,
- verifica `DASHBOARD_READ_API_KEY`,
- verifica CORS origins.

### 2) Errori firma/auth exchange
- controlla delega API signer su Hyperliquid,
- controlla `HYPERLIQUID_SIGNER_MODE=api_wallet`,
- controlla coerenza wallet master/signer.

### 3) Nessuna posizione aperta
- verifica risk constraints troppo stretti,
- verifica confidence LLM e decisioni hold,
- controlla log execution/risk rejection.

### 4) Dashboard non aggiornata
- usa Refresh,
- poi Restart,
- verifica raggiungibilità endpoint status/logs.

---

## Best practice operative

- Usa signer dedicato con capitale limitato.
- Non esporre mai key in log/screenshot.
- Mantieni `ALLOW_LOCALHOST_BYPASS=false` in produzione.
- Separa token read/admin.
- Monitora daily notional, margin usage, drawdown.
- Aggiorna periodicamente la runtime config in base alla volatilità.

---

Se vuoi estendere la documentazione, aggiungi:
- runbook incident response,
- policy rotazione signer,
- piano rollback produzione.