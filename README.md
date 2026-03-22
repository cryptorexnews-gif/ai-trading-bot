# Hyperliquid AI Trading Bot — Guida Completa (Setup, Avvio, Gestione)

Bot di trading per Hyperliquid con dashboard web in tempo reale, controllo runtime, gestione posizioni (SL/TP/trailing), log live e metriche.

---

## 1) Cosa fa il progetto

- Esegue cicli di analisi su coin selezionate
- Usa un LLM per decidere azioni di trading
- Applica gestione posizione (stop loss, take profit, trailing stop, break-even)
- Espone API Flask per dashboard e controllo bot
- Mostra dashboard React con stato, performance, posizioni e log

---

## 2) Prerequisiti

Assicurati di avere:

- Python 3.10+
- Node.js (LTS consigliato)
- Un wallet Hyperliquid con chiave privata
- Chiave API OpenRouter (se vuoi decisioni LLM)

---

## 3) Configurazione iniziale

### 3.1 File `.env`

Crea (o aggiorna) il file `.env` nella root del progetto con almeno:

- `HYPERLIQUID_WALLET_ADDRESS`
- `HYPERLIQUID_PRIVATE_KEY`
- `EXECUTION_MODE=live`
- `ENABLE_MAINNET_TRADING=true`
- `OPENROUTER_API_KEY` (per usare il modello LLM)
- `DASHBOARD_API_KEY` (protezione endpoint dashboard)

### 3.2 Nota importante su Vault

Il bot è configurato per operare in modalità **wallet + private key**.  
L’uso vault è disabilitato nella logica attuale, quindi non è richiesto configurare un vault address.

---

## 4) Avvio nell’interfaccia Dyad (consigliato qui)

Usa i pulsanti azione sopra la chat:

1. **Rebuild**  
   Da usare al primo avvio o dopo cambiamenti importanti.
2. **Restart**  
   Riavvia server/app dopo modifiche.
3. **Refresh**  
   Aggiorna la preview dashboard.

---

## 5) Comandi CMD (Windows) per esecuzione locale

> Usa questi comandi se stai eseguendo il progetto fuori dalla preview Dyad, da Prompt dei comandi.

### 5.1 Setup ambiente Python (prima volta)

```bat
cd C:\percorso\progetto\hyperliquid-ai-trading-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 5.2 Setup frontend (prima volta)

```bat
cd C:\percorso\progetto\hyperliquid-ai-trading-bot
npm install
```

### 5.3 Avvio API server

```bat
cd C:\percorso\progetto\hyperliquid-ai-trading-bot
.venv\Scripts\activate
python api_server.py
```

### 5.4 Avvio dashboard frontend (nuova finestra CMD)

```bat
cd C:\percorso\progetto\hyperliquid-ai-trading-bot
npm run dev
```

### 5.5 Avvio bot trading (nuova finestra CMD)

```bat
cd C:\percorso\progetto\hyperliquid-ai-trading-bot
.venv\Scripts\activate
python hyperliquid_bot_executable_orders.py
```

### 5.6 Esecuzione singolo ciclo (test sicuro)

```bat
cd C:\percorso\progetto\hyperliquid-ai-trading-bot
.venv\Scripts\activate
python hyperliquid_bot_executable_orders.py --single-cycle
```

### 5.7 Stop processi in CMD

- API / Bot: `CTRL + C` nella finestra relativa
- Frontend Vite: `CTRL + C` nella finestra frontend

---

## 6) Avvio bot e dashboard dalla UI

Dalla dashboard:

1. Vai in **Settings**
2. Sezione **Bot Process Control**
3. Premi **Start Bot**

Per fermarlo:
- Premi **Stop Bot** nella stessa sezione.

---

## 7) Configurazione runtime (senza riavvio codice)

In **Settings → Runtime Trading Controls** puoi:

- Cambiare strategia (`trend` / `scalping`)
- Selezionare le coin monitorate
- Salvare le impostazioni runtime

Le modifiche vengono applicate dal bot nel ciclo successivo.

---

## 8) Modalità operativa

### Live mode (soldi reali)
- `EXECUTION_MODE=live`
- `ENABLE_MAINNET_TRADING=true`
- Verifica sempre wallet, size e leva prima di avviare

---

## 9) Struttura dashboard

- **Overview**: saldo, PnL, drawdown, grafico principale
- **Settings**: controllo processo bot + runtime config
- **Positions**: posizioni aperte e gestione rischio
- **History**: storico trade, equity curve, export CSV
- **System**: circuit breaker, log live, diagnostica

---

## 10) Gestione quotidiana consigliata

1. Controlla che API e dashboard siano raggiungibili
2. Verifica modalità live attiva
3. Avvia il bot da **Settings**
4. Monitora:
   - `margin_usage`
   - posizioni aperte
   - log error/warning in **System**
5. Se cambi configurazioni importanti:
   - salva runtime config
   - eventualmente fai **Restart**

---

## 11) Troubleshooting rapido

### Il bot non apre posizioni
Controlla nei log se trovi:
- rifiuti risk manager
- ordini non filled
- problemi di connessione LLM/API

### Errori LLM/intermittenti
- Riprova con **Restart**
- Controlla che `OPENROUTER_API_KEY` sia presente
- Verifica timeout/retry nei log

### Dashboard non aggiornata
- Usa **Refresh**
- Se persiste, usa **Restart**

### Processo bot bloccato
- **Stop Bot** → **Start Bot**
- Se necessario, **Rebuild** e poi nuovo avvio

---

## 12) Sicurezza

- Non condividere mai `.env`
- Non esporre chiavi in log o screenshot
- Tieni `DASHBOARD_API_KEY` attiva
- In live, usa size prudenti e monitora sempre il rischio

---

## 13) Checklist prima di andare live

- [ ] Wallet e private key corretti
- [ ] `EXECUTION_MODE=live`
- [ ] `ENABLE_MAINNET_TRADING=true`
- [ ] Dashboard stabile (Overview/System senza errori critici)
- [ ] Runtime coin list validata
- [ ] Monitoraggio attivo durante i primi cicli

---

Per aggiornamenti futuri, mantieni questa guida allineata con la configurazione reale del bot (env, risk policy e flusso operativo).