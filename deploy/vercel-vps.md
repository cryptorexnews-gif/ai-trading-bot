# Deploy Production: Frontend su Vercel + Backend su VPS Cloud

Questa guida prepara l’architettura consigliata:

- **Frontend React/Vite** su **Vercel**
- **Backend Flask API + Bot** su **VPS cloud**
- Comunicazione sicura via HTTPS e CORS esplicito

---

## 1) Architettura consigliata

- Frontend pubblico: `https://tuo-frontend.vercel.app` (o dominio custom Vercel)
- Backend API pubblico: `https://api.tuodominio.com`
- Flask in ascolto locale sul VPS: `127.0.0.1:5000`
- Reverse proxy (Nginx/Caddy) sul VPS con TLS e inoltro a Flask

---

## 2) Variabili backend (`.env` sul VPS)

Imposta almeno:

- `EXECUTION_MODE=live`
- `ENABLE_MAINNET_TRADING=true`
- `API_HOST=127.0.0.1`
- `API_PORT=5000`
- `ALLOW_LOCALHOST_BYPASS=false`
- `CORS_ALLOWED_ORIGINS=https://tuo-frontend.vercel.app,https://tuo-dominio-frontend.com`

Sicurezza API:

- `DASHBOARD_API_KEY=<token-admin-lungo-casuale>`
- `DASHBOARD_READ_API_KEY=<token-readonly-lungo-casuale>`

Note:
- `DASHBOARD_API_KEY` (admin) serve per endpoint sensibili (es. start/stop bot, update runtime).
- `DASHBOARD_READ_API_KEY` serve ai soli endpoint GET dashboard (frontend pubblico).

---

## 3) Variabili frontend (Vercel Environment Variables)

Configura su Vercel:

- `VITE_API_BASE_URL=https://api.tuodominio.com/api`
- `VITE_DASHBOARD_TOKEN=<stesso-valore-di-DASHBOARD_READ_API_KEY>`

Note:
- Il frontend userà il token read-only.
- Non usare token admin nel frontend.

---

## 4) CORS e dominio

Nel backend:
- `CORS_ALLOWED_ORIGINS` deve contenere **solo** i domini frontend reali.
- Evita `*` in produzione live.

Esempio:
- `https://tuo-frontend.vercel.app`
- `https://app.tuodominio.com`

---

## 5) WebSocket in questa architettura

Con frontend su dominio diverso (Vercel) e backend su VPS, la dashboard funziona in modo affidabile via polling HTTP.
Se vuoi websocket cross-domain in futuro, conviene abilitarli dietro reverse proxy con una strategia auth dedicata.

---

## 6) Checklist finale prima del go-live

- [ ] Backend HTTPS attivo e certificato valido
- [ ] `ALLOW_LOCALHOST_BYPASS=false`
- [ ] `CORS_ALLOWED_ORIGINS` impostato ai soli domini frontend
- [ ] `DASHBOARD_API_KEY` impostata (admin)
- [ ] `DASHBOARD_READ_API_KEY` impostata (read-only)
- [ ] Vercel con `VITE_API_BASE_URL` e `VITE_DASHBOARD_TOKEN`
- [ ] Test dashboard completa (overview, history, positions, logs)
- [ ] Test endpoint admin solo con key admin