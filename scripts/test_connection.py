#!/usr/bin/env python3
"""
Test di connessione e configurazione per Hyperliquid Trading Bot.
Esegui PRIMA di avviare il bot per verificare che tutto sia configurato correttamente.

Usage:
    python scripts/test_connection.py
"""

import os
import sys
import time
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def mask(value: str, show: int = 6) -> str:
    if not value or len(value) < show * 2:
        return "NOT SET"
    return f"{value[:show]}...{value[-4:]}"


def print_header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def print_fail(msg: str) -> None:
    print(f"  ❌ {msg}")


def print_warn(msg: str) -> None:
    print(f"  ⚠️  {msg}")


def print_info(msg: str) -> None:
    print(f"  ℹ️  {msg}")


def test_env_vars() -> bool:
    """Test che le variabili d'ambiente obbligatorie siano configurate."""
    print_header("1. VARIABILI D'AMBIENTE")

    wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
    private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    mode = os.getenv("EXECUTION_MODE", "paper")
    mainnet = os.getenv("ENABLE_MAINNET_TRADING", "false")

    ok = True

    if wallet:
        print_ok(f"WALLET_ADDRESS: {mask(wallet)}")
    else:
        print_fail("HYPERLIQUID_WALLET_ADDRESS non configurato")
        ok = False

    if private_key:
        print_ok(f"PRIVATE_KEY: {mask(private_key)}")
    else:
        print_fail("HYPERLIQUID_PRIVATE_KEY non configurato")
        ok = False

    if openrouter_key:
        print_ok(f"OPENROUTER_API_KEY: {mask(openrouter_key)}")
    else:
        print_warn("OPENROUTER_API_KEY non configurato — LLM disabilitato, solo fallback hold")

    print_info(f"EXECUTION_MODE: {mode}")
    print_info(f"ENABLE_MAINNET_TRADING: {mainnet}")

    if mode == "live" and mainnet.lower() == "true":
        print_warn("⚡ MODALITÀ LIVE CON TRADING REALE ABILITATO ⚡")
    elif mode == "live":
        print_info("Modalità live ma ENABLE_MAINNET_TRADING=false → ordini simulati")
    else:
        print_ok("Modalità paper — ordini simulati (sicuro per test)")

    return ok


def test_wallet_match() -> bool:
    """Verifica che wallet address corrisponda alla chiave privata."""
    print_header("2. VALIDAZIONE WALLET")

    wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
    private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")

    if not wallet or not private_key:
        print_fail("Impossibile validare — credenziali mancanti")
        return False

    try:
        from eth_account import Account
        derived = Account.from_key(private_key).address

        if derived.lower() == wallet.lower():
            print_ok(f"Wallet address corrisponde alla chiave privata")
            print_info(f"Indirizzo derivato: {mask(derived)}")
            return True
        else:
            print_fail(f"MISMATCH! Wallet configurato: {mask(wallet)}")
            print_fail(f"Indirizzo derivato dalla chiave: {mask(derived)}")
            print_fail("Correggi HYPERLIQUID_WALLET_ADDRESS nel .env")
            return False
    except Exception as e:
        print_fail(f"Errore validazione wallet: {e}")
        return False


def test_hyperliquid_connection() -> bool:
    """Test connessione API Hyperliquid."""
    print_header("3. CONNESSIONE HYPERLIQUID")

    import requests

    base_url = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")
    timeout = int(os.getenv("HYPERLIQUID_INFO_TIMEOUT", "15"))

    # Test /info meta
    try:
        response = requests.post(
            f"{base_url}/info",
            json={"type": "meta"},
            timeout=timeout
        )
        if response.status_code == 200:
            meta = response.json()
            asset_count = len(meta.get("universe", []))
            print_ok(f"API /info raggiungibile — {asset_count} asset disponibili")
        else:
            print_fail(f"API /info ha risposto con status {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        print_fail(f"API /info timeout dopo {timeout}s")
        return False
    except requests.exceptions.ConnectionError:
        print_fail(f"Impossibile connettersi a {base_url}")
        return False

    # Test allMids
    try:
        response = requests.post(
            f"{base_url}/info",
            json={"type": "allMids"},
            timeout=timeout
        )
        if response.status_code == 200:
            mids = response.json()
            print_ok(f"Prezzi mid disponibili per {len(mids)} asset")
            for coin in ["BTC", "ETH", "SOL"]:
                if coin in mids:
                    print_info(f"  {coin}: ${mids[coin]}")
        else:
            print_fail(f"allMids ha risposto con status {response.status_code}")
            return False
    except Exception as e:
        print_fail(f"Errore allMids: {e}")
        return False

    # Test metaAndAssetCtxs (funding rates)
    try:
        response = requests.post(
            f"{base_url}/info",
            json={"type": "metaAndAssetCtxs"},
            timeout=timeout
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) >= 2:
                print_ok(f"Funding rates disponibili ({len(data[1])} asset contexts)")
            else:
                print_warn("metaAndAssetCtxs formato inatteso")
        else:
            print_warn(f"metaAndAssetCtxs status {response.status_code}")
    except Exception as e:
        print_warn(f"metaAndAssetCtxs errore: {e}")

    return True


def test_wallet_balance() -> bool:
    """Test saldo wallet su Hyperliquid."""
    print_header("4. SALDO WALLET")

    import requests

    wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
    base_url = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")
    timeout = int(os.getenv("HYPERLIQUID_INFO_TIMEOUT", "15"))

    if not wallet:
        print_fail("Wallet address non configurato")
        return False

    try:
        response = requests.post(
            f"{base_url}/info",
            json={"type": "clearinghouseState", "user": wallet},
            timeout=timeout
        )
        if response.status_code != 200:
            print_fail(f"Errore recupero stato wallet: status {response.status_code}")
            return False

        data = response.json()
        margin = data.get("marginSummary", {})
        balance = Decimal(str(margin.get("accountValue", "0")))
        available = Decimal(str(margin.get("withdrawable", "0")))
        margin_used = Decimal(str(margin.get("totalMarginUsed", "0")))

        print_ok(f"Saldo totale: ${balance:.2f}")
        print_info(f"Disponibile: ${available:.2f}")
        print_info(f"Margine usato: ${margin_used:.2f}")

        if balance > 0:
            usage_pct = (margin_used / balance * 100) if balance > 0 else Decimal("0")
            print_info(f"Uso margine: {usage_pct:.1f}%")
        else:
            print_warn("Saldo zero — deposita fondi su Hyperliquid per fare trading")

        # Posizioni aperte
        positions = data.get("assetPositions", [])
        open_positions = []
        for pos_wrapper in positions:
            pos = pos_wrapper.get("position", {})
            size = Decimal(str(pos.get("szi", "0")))
            if size != 0:
                coin = pos.get("coin", "?")
                entry = Decimal(str(pos.get("entryPx", "0")))
                pnl = Decimal(str(pos.get("unrealizedPnl", "0")))
                side = "LONG" if size > 0 else "SHORT"
                open_positions.append(f"{coin} {side} size={size} entry=${entry} pnl=${pnl:.4f}")

        if open_positions:
            print_info(f"Posizioni aperte: {len(open_positions)}")
            for p in open_positions:
                print_info(f"  {p}")
        else:
            print_ok("Nessuna posizione aperta")

        return True

    except Exception as e:
        print_fail(f"Errore recupero saldo: {e}")
        return False


def test_openrouter() -> bool:
    """Test connessione OpenRouter API."""
    print_header("5. CONNESSIONE OPENROUTER (LLM)")

    import requests

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv("LLM_MODEL", "anthropic/claude-opus-4")

    if not api_key:
        print_warn("OPENROUTER_API_KEY non configurato — LLM disabilitato")
        print_info("Il bot userà solo fallback 'hold' senza decisioni AI")
        return True  # Non è un errore critico

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with only the word 'ok'"}],
                "max_tokens": 5,
                "temperature": 0,
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print_ok(f"OpenRouter raggiungibile — modello: {model}")
            print_info(f"Test response: '{content.strip()}'")
            return True
        elif response.status_code == 401:
            print_fail("API key OpenRouter non valida (401 Unauthorized)")
            return False
        elif response.status_code == 402:
            print_fail("Credito OpenRouter insufficiente (402 Payment Required)")
            return False
        else:
            print_warn(f"OpenRouter ha risposto con status {response.status_code}")
            try:
                error_data = response.json()
                print_info(f"Dettaglio: {error_data.get('error', {}).get('message', 'N/A')}")
            except Exception:
                pass
            return False

    except requests.exceptions.Timeout:
        print_fail("OpenRouter timeout dopo 30s")
        return False
    except requests.exceptions.ConnectionError:
        print_fail("Impossibile connettersi a OpenRouter")
        return False
    except Exception as e:
        print_fail(f"Errore OpenRouter: {e}")
        return False


def test_trading_pairs() -> bool:
    """Verifica che le trading pairs configurate esistano su Hyperliquid."""
    print_header("6. TRADING PAIRS")

    import requests

    pairs_raw = os.getenv("TRADING_PAIRS", "BTC,ETH,SOL")
    pairs = [p.strip().upper() for p in pairs_raw.split(",") if p.strip()]
    base_url = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")

    try:
        response = requests.post(
            f"{base_url}/info",
            json={"type": "meta"},
            timeout=15
        )
        if response.status_code != 200:
            print_fail("Impossibile verificare trading pairs")
            return False

        meta = response.json()
        available = {a.get("name") for a in meta.get("universe", [])}

        valid = [p for p in pairs if p in available]
        invalid = [p for p in pairs if p not in available]

        if valid:
            print_ok(f"Pairs valide ({len(valid)}): {', '.join(valid)}")
        if invalid:
            print_fail(f"Pairs NON trovate su Hyperliquid: {', '.join(invalid)}")
            print_info("Rimuovile da TRADING_PAIRS nel .env")

        # Stima costo LLM per ciclo
        cycle_sec = int(os.getenv("DEFAULT_CYCLE_SEC", "120"))
        cost_per_call = 0.03  # Stima ~$0.03 per chiamata Opus
        calls_per_hour = (3600 / cycle_sec) * len(valid)
        cost_per_hour = calls_per_hour * cost_per_call
        cost_per_day = cost_per_hour * 24

        print_info(f"Ciclo: ogni {cycle_sec}s → ~{calls_per_hour:.0f} chiamate LLM/ora")
        print_info(f"Costo stimato: ~${cost_per_hour:.2f}/ora, ~${cost_per_day:.2f}/giorno")

        return len(invalid) == 0

    except Exception as e:
        print_fail(f"Errore verifica pairs: {e}")
        return False


def test_directories() -> bool:
    """Verifica che le directory necessarie esistano e siano scrivibili."""
    print_header("7. DIRECTORY E PERMESSI")

    import os

    dirs = ["state", "logs"]
    ok = True

    for d in dirs:
        if not os.path.exists(d):
            try:
                os.makedirs(d, mode=0o700, exist_ok=True)
                print_ok(f"Directory '{d}/' creata")
            except Exception as e:
                print_fail(f"Impossibile creare '{d}/': {e}")
                ok = False
        else:
            print_ok(f"Directory '{d}/' esiste")

        # Test scrittura
        test_file = os.path.join(d, ".write_test")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            print_ok(f"Directory '{d}/' è scrivibile")
        except Exception as e:
            print_fail(f"Directory '{d}/' NON è scrivibile: {e}")
            ok = False

    return ok


def test_dependencies() -> bool:
    """Verifica che tutte le dipendenze Python siano installate."""
    print_header("8. DIPENDENZE PYTHON")

    required = [
        ("requests", "requests"),
        ("eth_account", "eth-account"),
        ("Crypto.Hash.keccak", "pycryptodome"),
        ("msgpack", "msgpack"),
        ("dotenv", "python-dotenv"),
        ("flask", "flask"),
        ("flask_cors", "flask-cors"),
    ]

    ok = True
    for module_name, pip_name in required:
        try:
            parts = module_name.split(".")
            mod = __import__(parts[0])
            for part in parts[1:]:
                mod = getattr(mod, part)
            print_ok(f"{pip_name}")
        except (ImportError, AttributeError):
            print_fail(f"{pip_name} — installa con: pip install {pip_name}")
            ok = False

    return ok


def print_summary(results: dict) -> None:
    """Stampa riepilogo finale."""
    print_header("RIEPILOGO")

    all_ok = all(results.values())
    critical_ok = results.get("env", False) and results.get("wallet", False) and results.get("connection", False)

    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {name}")

    print()
    if all_ok:
        print("  🎉 TUTTO OK! Il bot è pronto per il test.")
        print()
        mode = os.getenv("EXECUTION_MODE", "paper")
        mainnet = os.getenv("ENABLE_MAINNET_TRADING", "false").lower()
        if mode == "paper":
            print("  📋 Prossimi passi:")
            print("     1. python hyperliquid_bot_executable_orders.py --single-cycle")
            print("        (esegue un singolo ciclo di test)")
            print()
            print("     2. python hyperliquid_bot_executable_orders.py")
            print("        (avvia il bot in continuo)")
            print()
            print("     3. In un altro terminale: python api_server.py")
            print("        (avvia la dashboard API)")
            print()
            print("     4. In un altro terminale: cd frontend && npm run dev")
            print("        (avvia la dashboard web su http://localhost:3000)")
        elif mainnet == "true":
            print("  ⚡ ATTENZIONE: Modalità LIVE con trading REALE abilitato!")
            print("  ⚡ Gli ordini verranno eseguiti con soldi veri!")
            print()
            print("  📋 Consiglio: testa prima con --single-cycle")
            print("     python hyperliquid_bot_executable_orders.py --single-cycle")
    elif critical_ok:
        print("  ⚠️  Alcuni test non critici sono falliti.")
        print("  Il bot può funzionare ma con funzionalità ridotte.")
    else:
        print("  ❌ Test critici falliti. Correggi gli errori prima di avviare il bot.")


def main():
    print()
    print("  🤖 HYPERLIQUID TRADING BOT — TEST CONFIGURAZIONE")
    print(f"  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    results["dependencies"] = test_dependencies()
    results["env"] = test_env_vars()
    results["wallet"] = test_wallet_match()
    results["connection"] = test_hyperliquid_connection()
    results["balance"] = test_wallet_balance()
    results["openrouter"] = test_openrouter()
    results["pairs"] = test_trading_pairs()
    results["directories"] = test_directories()

    print_summary(results)

    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()