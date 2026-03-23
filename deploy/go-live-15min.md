# Go-Live Checklist (15 minuti) — Hyperliquid Bot su VPS Aruba

## Minuto 0-2 — Sicurezza base
- Verifica che il server sia aggiornato e accessibile solo da utenti autorizzati.
- Mantieni aperte solo le porte strettamente necessarie (SSH + web).

## Minuto 2-4 — File `.env`
Compila tutti i campi critici:
- `HYPERLIQUID_WALLET_ADDRESS`
- `HYPERLIQUID_PRIVATE_KEY`
- `OPENROUTER_API_KEY`
- `DASHBOARD_API_KEY`

Conferma valori produzione:
- `EXECUTION_MODE=live`
- `ENABLE_MAINNET_TRADING=true`
- `ALLOW_LOCALHOST_BYPASS=false` (consigliato in produzione esterna)
- `CORS_ALLOWED_ORIGINS` con il tuo dominio reale (niente wildcard)

## Minuto 4-6 — Risk prudente iniziale
Mantieni il profilo conservativo per il primo avvio:
- leva bassa/moderata
- limite giornaliero contenuto
- max trade per ciclo contenuto
- drawdown e soglia emergenza attivi

## Minuto 6-8 — Deploy container
- Avvia stack con `docker-compose.yml`.
- Verifica che i 4 servizi siano in stato healthy/running:
  - `hyperliquid_api`
  - `hyperliquid_bot`
  - `hyperliquid_frontend`
  - `hyperliquid_nginx`

## Minuto 8-10 — Test funzionali
Controlla:
- Dashboard raggiungibile via Nginx.
- Endpoint health API risponde.
- Bot visibile in dashboard (stato, ciclo, log, circuit breaker).

## Minuto 10-12 — Cutover HTTPS
- Imposta il tuo dominio nel file `deploy/nginx/default-https.conf` (sostituisci `your-domain.com`).
- Usa l’override `docker-compose.https.yml` quando i certificati sono pronti.
- Conferma redirect HTTP→HTTPS e certificato valido.

## Minuto 12-14 — Hardening finale
- Conferma che API key dashboard sia obbligatoria.
- Conferma che nessun segreto compaia nei log.
- Verifica che i websocket (`/ws/`) funzionino anche su HTTPS.

## Minuto 14-15 — Avvio controllato
- Esegui primo periodo live con size ridotte.
- Monitora i primi cicli senza aumentare subito il rischio.
- Aumenta gradualmente solo dopo stabilità operativa.

---

## Post go-live (prima ora)
- Controlla periodicamente:
  - errori API/LLM
  - execution failures
  - margin usage
  - drawdown
- Se qualcosa è anomalo: ferma subito il bot e rivedi `.env`/limiti.