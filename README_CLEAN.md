# Hyperliquid Trading Bot - Versione Pulita

Progetto pulito e ottimizzato contenente solo i componenti essenziali.

## 🎯 Cosa è stato mantenuto

### Core Trading Bot
- `hyperliquid_bot_executable_orders.py` - Entry point principale
- `config/bot_config.py` - Configurazione centralizzata
- `cycle_orchestrator.py` - Orchestrazione cicli trading
- `exchange_client.py` - Client API Hyperliquid
- `llm_engine.py` - Integrazione Claude Opus 4.6
- `execution_engine.py` - Esecuzione ordini
- `risk_manager.py` - Gestione rischio
- `position_manager.py` - SL/TP/Trailing/Break-even
- `technical_analyzer_simple.py` - Indicatori tecnici

### API Server
- `api_server.py` - Server Flask
- `api/` - Tutti i blueprint e route
- Autenticazione JWT e CORS configurati

### Frontend Dashboard
- `frontend/` - Dashboard React completa
- Chart in tempo reale con Lightweight Charts
- Monitoraggio posizioni e performance
- Log viewer con sanitizzazione

### Utilità
- `utils/` - Funzioni helper essenziali
- `state/` - Persistenza stato
- `logs/` - Logging strutturato

## 🚀 Avvio Rapido

### 1. Installa dipendenze
```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 2. Configura .env
```bash
cp .env.example .env
# Modifica .env con le tue chiavi
```

### 3. Test
```bash
python hyperliquid_bot_executable_orders.py --single-cycle
```

### 4. Avvia tutto (3 terminali)
```bash
# Terminale 1: Bot trading
python hyperliquid_bot_executable_orders.py

# Terminale 2: API Server
python api_server.py

# Terminale 3: Dashboard
cd frontend && npm run dev
```

## 🌐 Collegamenti
- **Dashboard**: http://localhost:3000
- **API Server**: http://localhost:5000
- **Health Check**: http://localhost:5000/api/health

## 📊 Funzionalità Mantenute

### Trading
- Decisioni AI con Claude Opus 4.6
- SL/TP/Trailing Stop/Break-even automatici
- Gestione rischio multi-livello
- Verifica esecuzione ordini
- Notifiche Telegram

### Dashboard
- Chart candele in tempo reale
- Monitoraggio posizioni
- Curva equity portfolio
- Log viewer sanitizzato
- Export CSV trade history

### Sicurezza
- Autenticazione API Key
- Sanitizzazione log
- Circuit breakers
- Rate limiting
- Validazione input

## 🛠️ Script Utilità

### Pulizia progetto
```bash
chmod +x run_cleanup.sh
./run_cleanup.sh
```

### Test connessione
```bash
python scripts/test_connection.py
```

### Verifica posizioni
```bash
python check_current_positions.py
```

## ⚙️ Configurazione Minima (.env)
```env
# REQUIRED
HYPERLIQUID_WALLET_ADDRESS=0x...
HYPERLIQUID_PRIVATE_KEY=0x...
DASHBOARD_API_KEY=your-secure-key
VITE_DASHBOARD_API_KEY=your-secure-key

# OPTIONAL (defaults to paper trading)
EXECUTION_MODE=paper
ENABLE_MAINNET_TRADING=false
TRADING_PAIRS=BTC,ETH,SOL
```

## 📈 Performance
- **Ciclo trading**: 30-300s (adattivo)
- **LLM calls**: ~2-3s per decisione
- **Dashboard update**: 5s polling
- **Log retention**: 100 trade, 500 equity snapshots

## 🔧 Troubleshooting

### "DASHBOARD_API_KEY not set"
```bash
# Genera una chiave
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Aggiungi a .env in DASHBOARD_API_KEY e VITE_DASHBOARD_API_KEY
```

### Porte occupate
Modifica in `.env`:
```env
API_SERVER_PORT=5001
VITE_PORT=3001
```

### Dipendenze mancanti
```bash
pip install -r requirements.txt --force
cd frontend && npm install --force && cd ..
```

## 📄 Licenza
MIT - Uso libero per scopi personali e commerciali.

**Buon Trading! 🚀**