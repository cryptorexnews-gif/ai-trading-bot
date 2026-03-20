# Hyperliquid Trading Bot - Versione Minimale

## Installazione
```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

## Configurazione
1. Copia `.env.example` in `.env`
2. Modifica le variabili d'ambiente
3. Test: `python hyperliquid_bot_executable_orders.py --single-cycle`

## Avvio
```bash
# Terminale 1: Bot
python hyperliquid_bot_executable_orders.py

# Terminale 2: API Server
python api_server.py

# Terminale 3: Dashboard
cd frontend && npm run dev
```

## Dashboard
- URL: http://localhost:3000
- API: http://localhost:5000