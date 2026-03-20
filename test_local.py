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
    
    with open(".env", "r") as f:
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
    try:
        import requests
        import eth_account
        import flask
        print("✅ Dipendenze Python installate")
        return True
    except ImportError as e:
        print(f"❌ Dipendenza Python mancante: {e}")
        print("   Installa con: pip install -r requirements.txt")
        return False

def check_node_deps():
    """Verifica le dipendenze Node.js."""
    node_modules = Path("node_modules")
    if not node_modules.exists():
        print("❌ node_modules non trovato")
        print("   Installa con: npm install")
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
        text=True
    )
    
    # Attendi che il backend sia pronto
    for _ in range(30):  # 30 tentativi, 1 secondo ciascuno
        try:
            response = requests.get("http://localhost:5000/api/health", timeout=1)
            if response.status_code == 200:
                print("✅ Backend API server attivo su http://localhost:5000")
                return backend_proc
        except:
            time.sleep(1)
    
    print("❌ Backend non risponde dopo 30 secondi")
    backend_proc.terminate()
    return None

def start_frontend():
    """Avvia il frontend dashboard."""
    print("🚀 Avvio frontend dashboard...")
    frontend_proc = subprocess.Popen(
        ["npm", "run", "dev"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=True
    )
    
    # Attendi che il frontend sia pronto
    for _ in range(30):
        try:
            response = requests.get("http://localhost:3000", timeout=1)
            if response.status_code == 200:
                print("✅ Frontend dashboard attivo su http://localhost:3000")
                return frontend_proc
        except:
            time.sleep(1)
    
    print("❌ Frontend non risponde dopo 30 secondi")
    frontend_proc.terminate()
    return None

def test_api_endpoints():
    """Testa gli endpoint API."""
    print("🔍 Test endpoint API...")
    
    # Leggi la chiave API dal .env
    api_key = None
    with open(".env", "r") as f:
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
        ("/api/portfolio", "GET"),
        ("/api/trades?limit=5", "GET"),
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

def main():
    print("=" * 60)
    print("🤖 TEST CONFIGURAZIONE LOCALE HYPERLIQUID BOT")
    print("=" * 60)
    
    # Verifica file .env
    if not check_env_file():
        return 1
    
    # Verifica dipendenze Python
    if not check_python_deps():
        return 1
    
    # Verifica dipendenze Node.js
    if not check_node_deps():
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
    print("   🌐 API Docs: http://localhost:5000/api/health")
    print("\n📋 Per avviare il bot di trading:")
    print("   python hyperliquid_bot_executable_orders.py --single-cycle")
    print("\n🛑 Premi Ctrl+C per fermare i servizi")
    
    try:
        # Mantieni i processi attivi
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\n🛑 Fermo i servizi...")
        backend_proc.terminate()
        frontend_proc.terminate()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())