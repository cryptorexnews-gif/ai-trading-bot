#!/usr/bin/env python3
"""
Test rapido per verificare che tutto funzioni in locale.
"""

import os
import sys
import subprocess
import time
import requests
from pathlib import Path

def check_env_file():
    """Verifica che il file .env esista e contenga le variabili necessarie."""
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ File .env non trovato!")
        print("   Copia .env.example in .env e modifica le variabili:")
        print("   cp .env.example .env")
        return False
    
    try:
        with open(".env", "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        # Prova con un encoding diverso per Windows
        with open(".env", "r", encoding="latin-1") as f:
            content = f.read()
    
    required_vars = [
        "HYPERLIQUID_WALLET_ADDRESS",
        "HYPERLIQUID_PRIVATE_KEY",
        "DASHBOARD_API_KEY",
        "VITE_DASHBOARD_API_KEY"
    ]
    
    missing = []
    for var in required_vars:
        if f"{var}=" not in content:
            missing.append(var)
    
    if missing:
        print(f"❌ Variabili mancanti in .env: {', '.join(missing)}")
        return False
    
    print("✅ File .env configurato correttamente")
    return True

def check_python_deps():
    """Verifica le dipendenze Python."""
    deps = [
        ("requests", "requests"),
        ("eth_account", "eth-account"),
        ("Crypto.Hash.keccak", "pycryptodome"),
        ("msgpack", "msgpack-python"),
        ("dotenv", "python-dotenv"),
        ("flask", "flask"),
        ("flask_cors", "flask-cors"),
    ]
    
    ok_count = 0
    for module_name, pip_name in deps:
        try:
            parts = module_name.split(".")
            mod = __import__(parts[0])
            for part in parts[1:]:
                mod = getattr(mod, part)
            print(f"✅ {pip_name}")
            ok_count += 1
        except (ImportError, AttributeError):
            print(f"❌ {pip_name} → pip install {pip_name}")
    
    print_info(f"{ok_count}/{len(deps)} deps OK")
    return ok_count == len(deps)

def check_node_deps():
    """Verifica le dipendenze Node.js."""
    node_modules = Path("node_modules")
    if not node_modules.exists():
        print("❌ node_modules non trovato")
        print("   Installa con: npm install --force")
        return False
    
    print("✅ Dipendenze Node.js installate")
    return True

def start_backend():
    """Avvia il backend API server."""
    print("🚀 Avvio backend API server...")
    backend_proc = subprocess.Popen(
        [sys.executable, "api_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )
    
    # Attendi che il backend sia pronto
    for i in range(30):  # 30 tentativi, 1 secondo ciascuno
        try:
            response = requests.get("http://localhost:5000/api/health", timeout=1)
            if response.status_code == 200:
                print("✅ Backend API server attivo su http://localhost:5000")
                return backend_proc
        except:
            if i % 5 == 0:
                print(f"⏳ Attendo backend... ({i+1}/30)")
            time.sleep(1)
    
    print("❌ Backend non risponde dopo 30 secondi")
    backend_proc.terminate()
    return None

def start_frontend():
    """Avvia il frontend dashboard."""
    print("🚀 Avvio frontend dashboard...")
    
    # Usa PowerShell su Windows
    if sys.platform == "win32":
        frontend_proc = subprocess.Popen(
            ["powershell", "-Command", "npm run dev"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        frontend_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    
    # Attendi che il frontend sia pronto
    for i in range(30):
        try:
            response = requests.get("http://localhost:3000", timeout=1)
            if response.status_code == 200:
                print("✅ Frontend dashboard attivo su http://localhost:3000")
                return frontend_proc
        except:
            if i % 5 == 0:
                print(f"⏳ Attendo frontend... ({i+1}/30)")
            time.sleep(1)
    
    print("❌ Frontend non risponde dopo 30 secondi")
    frontend_proc.terminate()
    return None

def test_api_endpoints():
    """Testa gli endpoint API."""
    print("🔍 Test endpoint API...")
    
    # Leggi la chiave API dal .env
    api_key = None
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("DASHBOARD_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    except UnicodeDecodeError:
        with open(".env", "r", encoding="latin-1") as f:
            for line in f:
                if line.startswith("DASHBOARD_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    
    if not api_key:
        print("❌ DASHBOARD_API_KEY non trovata in .env")
        return False
    
    headers = {"X-API-Key": api_key}
    endpoints = [
        ("/api/health", "GET"),
        ("/api/config", "GET"),
    ]
    
    all_ok = True
    for endpoint, method in endpoints:
        try:
            if method == "GET":
                response = requests.get(f"http://localhost:5000{endpoint}", headers=headers, timeout=5)
            else:
                response = requests.post(f"http://localhost:5000{endpoint}", headers=headers, timeout=5)
            
            if response.status_code == 200:
                print(f"✅ {endpoint}: OK")
            else:
                print(f"❌ {endpoint}: HTTP {response.status_code}")
                all_ok = False
        except Exception as e:
            print(f"❌ {endpoint}: {e}")
            all_ok = False
    
    return all_ok

def print_ok(msg: str) -> None:
    print(f"✅ {msg}")

def print_fail(msg: str) -> None:
    print(f"❌ {msg}")

def print_warn(msg: str) -> None:
    print(f"⚠️  {msg}")

def print_info(msg: str) -> None:
    print(f"ℹ️  {msg}")

def main():
    print("=" * 60)
    print("🤖 TEST CONFIGURAZIONE LOCALE HYPERLIQUID BOT")
    print("=" * 60)
    
    # Verifica file .env
    if not check_env_file():
        return 1
    
    # Verifica dipendenze Python
    if not check_python_deps():
        print_warn("Alcune dipendenze Python mancano. Installale con:")
        print("   pip install -r requirements.txt")
        return 1
    
    # Verifica dipendenze Node.js
    if not check_node_deps():
        print_warn("Dipendenze Node.js mancanti. Installa con:")
        print("   npm install --force")
        return 1
    
    # Avvia backend
    backend_proc = start_backend()
    if not backend_proc:
        return 1
    
    # Test endpoint API
    if not test_api_endpoints():
        backend_proc.terminate()
        return 1
    
    # Avvia frontend
    frontend_proc = start_frontend()
    if not frontend_proc:
        backend_proc.terminate()
        return 1
    
    print("\n" + "=" * 60)
    print("🎉 TUTTO FUNZIONA!")
    print("=" * 60)
    print("\n🔗 Collegamenti:")
    print("   📊 Dashboard: http://localhost:3000")
    print("   🌐 API Server: http://localhost:5000")
    print("\n📋 Per avviare il bot di trading:")
    print("   python hyperliquid_bot_executable_orders.py --single-cycle")
    print("\n🛑 Premi Ctrl+C per fermare i servizi")
    
    try:
        # Mantieni i processi attivi
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\n🛑 Fermo i servizi...")
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(backend_proc.pid)], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(frontend_proc.pid)], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            backend_proc.terminate()
            frontend_proc.terminate()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())