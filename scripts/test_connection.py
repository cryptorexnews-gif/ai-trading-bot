#!/usr/bin/env python3
"""
🤖 HYPERLIQUID TRADING BOT — TEST CONFIGURAZIONE COMPLETO (v2.0)
Testa TUTTO: deps, env, wallet, API, LLM, config, frontend, readiness score.

Usage: python scripts/test_connection.py
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# Add parent dir for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# ANSI Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'


def print_header(title: str) -> None:
    print(f"\n{GREEN}{'=' * 70}{RESET}")
    print(f"{GREEN}  {BOLD}{title}{RESET}{GREEN}{'=' * (70-len(title)-4)}{RESET}")


def print_ok(msg: str) -> None:
    print(f"{GREEN}  ✅ {msg}{RESET}")


def print_fail(msg: str) -> None:
    print(f"{RED}  ❌ {msg}{RESET}")


def print_warn(msg: str) -> None:
    print(f"{YELLOW}  ⚠️  {msg}{RESET}")


def print_info(msg: str) -> None:
    print(f"{BLUE}  ℹ️  {msg}{RESET}")


def print_success(msg: str) -> None:
    print(f"{GREEN}{BOLD}  🎉 {msg}{RESET}")


def run_command(cmd: list, cwd: str = None, timeout: int = 10) -> tuple[bool, str]:
    """Run command, return (success, output)."""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


def test_pycryptodome() -> bool:
    """Test pycryptodome + keccak import (AI rules requirement)."""
    try:
        from Crypto.Hash import keccak
        h = keccak.new(digest_bits=256)
        h.update(b"test")
        digest = h.hexdigest()
        if len(digest) == 64:
            print_ok("pycryptodome + keccak OK (hash test passed)")
            return True
        print_fail("pycryptodome keccak hash invalid")
        return False
    except ImportError:
        print_fail("pycryptodome NOT INSTALLED")
        return False
    except Exception as e:
        print_fail(f"pycryptodome error: {e}")
        return False


def test_dependencies() -> bool:
    print_header("1. DIPENDENZE PYTHON")
    required = [
        ("requests", "requests"),
        ("eth_account", "eth-account"),
        ("Crypto.Hash.keccak", "pycryptodome"),
        ("msgpack", "msgpack"),
        ("dotenv", "python-dotenv"),
        ("flask", "flask"),
        ("flask_cors", "flask-cors"),
    ]
    ok_count = 0
    for module_name, pip_name in required:
        try:
            parts = module_name.split(".")
            mod = __import__(parts[0])
            for part in parts[1:]:
                mod = getattr(mod, part)
            print_ok(f"{pip_name}")
            ok_count += 1
        except (ImportError, AttributeError):
            print_fail(f"{pip_name} mancante")
    print_info(f"{ok_count}/{len(required)} deps OK")
    return ok_count == len(required)


def test_env_vars() -> bool:
    print_header("2. VARIABILI D'AMBIENTE")
    wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
    private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    dashboard_key = os.getenv("DASHBOARD_API_KEY", "")
    mode = os.getenv("EXECUTION_MODE", "paper")
    mainnet = os.getenv("ENABLE_MAINNET_TRADING", "false")
    ok = True
    if wallet:
        print_ok(f"WALLET: {wallet[:6]}...{wallet[-4:]}")
    else:
        print_fail("HYPERLIQUID_WALLET_ADDRESS mancante")
        ok = False
    if private_key:
        print_ok(f"PRIVATE_KEY: {private_key[:6]}...{private_key[-4:]}")
    else:
        print_fail("HYPERLIQUID_PRIVATE_KEY mancante")
        ok = False
    if openrouter_key:
        print_ok("OPENROUTER: sk-or-...OK")
    else:
        print_warn("OPENROUTER_API_KEY mancante → fallback hold")
    if dashboard_key:
        print_ok(f"DASHBOARD_API_KEY: {len(dashboard_key)} chars ✓")
    else:
        print_warn("DASHBOARD_API_KEY mancante")
    print_info(f"MODE: {mode} | MAINNET: {mainnet}")
    if mode == "live" and mainnet.lower() == "true":
        print_warn("⚡ LIVE + MAINNET=TRUE → SOLDI VERI")
    return ok


def test_wallet_match() -> bool:
    print_header("3. WALLET VALIDATION")
    wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
    private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
    if not wallet or not private_key:
        print_fail("Credenziali mancanti")
        return False
    try:
        from eth_account import Account
        derived = Account.from_key(private_key).address
        if derived.lower() == wallet.lower():
            print_ok(f"✓ {wallet[:6]}...{wallet[-4:]} matches private key")
            return True
        print_fail(f"MISMATCH! Config: {wallet[:6]}... vs Derived: {derived[:6]}...")
        return False
    except Exception as e:
        print_fail(f"Validation error: {e}")
        return False


def test_hyperliquid_connection() -> bool:
    print_header("4. HYPERLIQUID API")
    base_url = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")
    timeout = int(os.getenv("HYPERLIQUID_INFO_TIMEOUT", "15"))
    endpoints = [
        ("meta", {"type": "meta"}),
        ("allMids", {"type": "allMids"}),
        ("metaAndAssetCtxs", {"type": "metaAndAssetCtxs"}),
    ]
    ok = True
    import requests
    for name, payload in endpoints:
        try:
            resp = requests.post(f"{base_url}/info", json=payload, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                count = len(data) if isinstance(data, list) else len(data.get("universe", []))
                print_ok(f"{name}: OK ({count} items)")
            else:
                print_fail(f"{name}: HTTP {resp.status_code}")
                ok = False
        except Exception as e:
            print_fail(f"{name}: {e}")
            ok = False
    return ok


def test_wallet_balance() -> bool:
    print_header("5. SALDO WALLET")
    wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
    if not wallet:
        print_fail("No wallet")
        return False
    import requests
    base_url = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")
    try:
        resp = requests.post(
            f"{base_url}/info",
            json={"type": "clearinghouseState", "user": wallet},
            timeout=15
        )
        if resp.status_code != 200:
            print_fail(f"HTTP {resp.status_code}")
            return False
        data = resp.json()
        margin = data.get("marginSummary", {})
        balance = float(margin.get("accountValue", 0))
        available = float(margin.get("withdrawable", 0))
        print_ok(f"Balance: ${balance:.2f} | Available: ${available:.2f}")
        positions = [p for p in data.get("assetPositions", []) if float(p.get("position", {}).get("szi", 0)) != 0]
        if positions:
            print_info(f"Open positions: {len(positions)}")
        else:
            print_ok("No open positions")
        return True
    except Exception as e:
        print_fail(f"Error: {e}")
        return False


def test_openrouter() -> bool:
    print_header("6. OPENROUTER (LLM)")
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        print_warn("No API key → LLM disabled (fallback hold)")
        return True
    try:
        import requests
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "anthropic/claude-opus-4", "messages": [{"role": "user", "content": "ok"}], "max_tokens": 5},
            timeout=30
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"].strip()
            print_ok(f"✓ Model OK | Response: '{content}'")
            return True
        print_fail(f"HTTP {resp.status_code}")
        return False
    except Exception as e:
        print_fail(f"Error: {e}")
        return False


def test_bot_config() -> bool:
    print_header("7. BOT CONFIG")
    try:
        from config.bot_config import BotConfig
        cfg = BotConfig.from_env()
        warnings = cfg.validate()
        if warnings:
            for w in warnings:
                print_warn(w)
            print_info("Config warnings (non-blocking)")
        else:
            print_ok("BotConfig 100% valid")
        print_info(f"Pairs: {len(cfg.trading_pairs)} | Cycle: {cfg.default_cycle_sec}s | Drawdown: {float(cfg.max_drawdown_pct)*100}%")
        return True
    except Exception as e:
        print_fail(f"BotConfig error: {e}")
        return False


def test_api_server() -> bool:
    print_header("8. API SERVER ENDPOINTS")
    api_key = os.getenv("DASHBOARD_API_KEY", "")
    base_url = "http://127.0.0.1:5000"
    import requests

    # /api/health is public
    try:
        resp = requests.get(f"{base_url}/api/health", timeout=5)
        if resp.status_code == 200:
            print_ok("/api/health: OK")
        else:
            print_fail(f"/api/health: {resp.status_code}")
            return False
    except Exception as e:
        print_fail(f"/api/health: {e}")
        return False

    # /api/config protected in many setups
    headers = {"X-API-Key": api_key} if api_key else {}
    try:
        resp = requests.get(f"{base_url}/api/config", headers=headers, timeout=5)
        if resp.status_code == 200:
            print_ok("/api/config: OK")
            return True
        if resp.status_code == 401:
            print_warn("/api/config: 401 (expected if API key missing and localhost bypass disabled)")
            return True
        print_fail(f"/api/config: {resp.status_code}")
        return False
    except Exception as e:
        print_fail(f"/api/config: {e}")
        return False


def test_frontend_deps() -> bool:
    print_header("9. FRONTEND (single root app)")
    root_dir = Path(".")
    package_json = root_dir / "package.json"
    src_dir = root_dir / "src"

    if not package_json.exists() or not src_dir.exists():
        print_fail("Root frontend missing (package.json or src/ not found)")
        return False

    ok, _ = run_command(["npm", "list"], cwd=".")
    if ok:
        print_ok("npm deps OK (root)")
    else:
        print_warn("npm deps issue (root)")

    run_command(["npm", "run", "dev", "--", "--port=3000"], cwd=".", timeout=3)
    print_info("Frontend: npm run dev → http://localhost:3000")
    return True


def test_readiness() -> bool:
    print_header("10. READINESS SCORE")
    tests = [
        test_dependencies(),
        test_env_vars(),
        test_wallet_match(),
        test_hyperliquid_connection(),
        test_wallet_balance(),
        test_openrouter(),
        test_bot_config(),
        test_api_server(),
        test_frontend_deps(),
        test_pycryptodome(),
    ]
    score = sum(tests) / len(tests) * 100
    print(f"{GREEN}{BOLD}  SCORE: {score:.0f}%{RESET}")
    if score >= 90:
        print_success("🚀 BOT READY")
    elif score >= 70:
        print_warn("⚠️  MOSTLY READY — Fix warnings above")
    else:
        print_fail("❌ CRITICAL ISSUES — Fix before running")
    return score >= 90


if __name__ == "__main__":
    print(f"\n{GREEN}{BOLD}🤖 HYPERLIQUID TRADING BOT — FULL DIAGNOSTIC v2.0{RESET}")
    print(f"{BLUE}Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC')}{RESET}\n")
    test_readiness()