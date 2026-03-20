#!/usr/bin/env python3
"""
Script per pulire il progetto Hyperliquid Trading Bot rimuovendo file non necessari.
Mantiene solo il core del bot, l'API server e il frontend essenziale.
"""

import os
import shutil
import sys
from pathlib import Path

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

def print_warn(msg: str) -> None:
    print(f"{YELLOW}  ⚠️  {msg}{RESET}")

def print_info(msg: str) -> None:
    print(f"{BLUE}  ℹ️  {msg}{RESET}")

def print_error(msg: str) -> None:
    print(f"{RED}  ❌ {msg}{RESET}")

def get_confirmation(prompt: str) -> bool:
    """Chiedi conferma all'utente."""
    print(f"\n{YELLOW}{prompt} (y/N): {RESET}", end="")
    response = input().strip().lower()
    return response in ['y', 'yes', 'si', 's']

def analyze_project_structure():
    """Analizza la struttura del progetto e identifica file non necessari."""
    print_header("ANALISI STRUTTURA PROGETTO")
    
    # File essenziali da mantenere
    essential_files = {
        # Core del bot
        'hyperliquid_bot_executable_orders.py',
        'config/bot_config.py',
        'cycle_orchestrator.py',
        'portfolio_service.py',
        'exchange_client.py',
        'llm_engine.py',
        'execution_engine.py',
        'risk_manager.py',
        'position_manager.py',
        'correlation_engine.py',
        'technical_analyzer_simple.py',
        'order_verifier.py',
        'state_store.py',
        'bot_live_writer.py',
        'notifier.py',
        'models.py',
        
        # API Server
        'api_server.py',
        'api/__init__.py',
        'api/config.py',
        'api/auth.py',
        'api/json_provider.py',
        'api/helpers.py',
        'api/routes/__init__.py',
        'api/routes/health.py',
        'api/routes/bot.py',
        'api/routes/trading.py',
        'api/routes/market.py',
        'api/routes/logs.py',
        'api/routes/metrics.py',
        
        # Utils essenziali
        'utils/__init__.py',
        'utils/file_io.py',
        'utils/http.py',
        'utils/circuit_breaker.py',
        'utils/rate_limiter.py',
        'utils/retry.py',
        'utils/decimals.py',
        'utils/validation.py',
        'utils/metrics.py',
        'utils/health.py',
        'utils/logging_config.py',
        
        # Frontend essenziale
        'frontend/package.json',
        'frontend/vite.config.js',
        'frontend/tailwind.config.js',
        'frontend/postcss.config.js',
        'frontend/index.html',
        'frontend/src/main.jsx',
        'frontend/src/App.jsx',
        'frontend/src/index.css',
        'frontend/src/hooks/useApi.js',
        'frontend/src/components/ErrorBoundary.jsx',
        'frontend/src/components/StatusBadge.jsx',
        'frontend/src/components/StatCard.jsx',
        'frontend/src/components/PositionsTable.jsx',
        'frontend/src/components/ManagedPositions.jsx',
        'frontend/src/components/TradeHistory.jsx',
        'frontend/src/components/EquityChart.jsx',
        'frontend/src/components/TradingView.jsx',
        'frontend/src/components/CircuitBreakerStatus.jsx',
        'frontend/src/components/LogViewer.jsx',
        'frontend/src/components/DrawdownBar.jsx',
        'frontend/src/components/ConnectionStatus.jsx',
        'frontend/src/components/ExportButton.jsx',
        
        # File di configurazione
        'requirements.txt',
        '.env.example',
        '.gitignore',
        'README.md',
        'AI_RULES.md',
        'session_report.md',
    }
    
    # Directory da mantenere
    essential_dirs = {
        'config',
        'api',
        'api/routes',
        'utils',
        'frontend',
        'frontend/src',
        'frontend/src/components',
        'frontend/src/hooks',
        'state',
        'logs',
    }
    
    # File da eliminare (non essenziali)
    files_to_remove = []
    dirs_to_remove = []
    
    # Analizza directory corrente
    for item in Path('.').iterdir():
        if item.name.startswith('.'):
            continue
            
        if item.is_file():
            if item.name not in essential_files and item.suffix in ['.py', '.js', '.jsx', '.ts', '.tsx', '.md', '.txt']:
                files_to_remove.append(str(item))
        elif item.is_dir():
            if item.name not in essential_dirs and item.name not in ['__pycache__', 'node_modules', '.vscode', '.idea']:
                dirs_to_remove.append(str(item))
    
    return {
        'files_to_remove': files_to_remove,
        'dirs_to_remove': dirs_to_remove,
        'essential_files': essential_files,
        'essential_dirs': essential_dirs
    }

def remove_files_and_dirs(files_to_remove, dirs_to_remove):
    """Rimuovi file e directory non necessari."""
    print_header("RIMOZIONE FILE NON NECESSARI")
    
    removed_count = 0
    error_count = 0
    
    # Rimuovi file
    for file_path in files_to_remove:
        try:
            os.remove(file_path)
            print_ok(f"Rimosso: {file_path}")
            removed_count += 1
        except Exception as e:
            print_error(f"Errore rimozione {file_path}: {e}")
            error_count += 1
    
    # Rimuovi directory (ricorsivamente)
    for dir_path in dirs_to_remove:
        try:
            shutil.rmtree(dir_path)
            print_ok(f"Rimosso directory: {dir_path}")
            removed_count += 1
        except Exception as e:
            print_error(f"Errore rimozione directory {dir_path}: {e}")
            error_count += 1
    
    # Pulisci __pycache__
    for root, dirs, files in os.walk('.'):
        for dir_name in dirs:
            if dir_name == '__pycache__':
                cache_dir = os.path.join(root, dir_name)
                try:
                    shutil.rmtree(cache_dir)
                    print_ok(f"Rimosso __pycache__: {cache_dir}")
                except:
                    pass
    
    print_info(f"\nRimossi {removed_count} elementi, {error_count} errori")
    return removed_count, error_count

def cleanup_frontend():
    """Pulisci il frontend rimuovendo componenti non necessari."""
    print_header("PULIZIA FRONTEND")
    
    frontend_src = Path('frontend/src')
    if not frontend_src.exists():
        print_warn("Directory frontend/src non trovata")
        return
    
    # Componenti essenziali da mantenere
    essential_components = {
        'ErrorBoundary.jsx',
        'StatusBadge.jsx',
        'StatCard.jsx',
        'PositionsTable.jsx',
        'ManagedPositions.jsx',
        'TradeHistory.jsx',
        'EquityChart.jsx',
        'TradingView.jsx',
        'CircuitBreakerStatus.jsx',
        'LogViewer.jsx',
        'DrawdownBar.jsx',
        'ConnectionStatus.jsx',
        'ExportButton.jsx',
    }
    
    # Directory componenti trading (da mantenere se esiste)
    trading_dir = frontend_src / 'components' / 'trading'
    if trading_dir.exists():
        essential_components.update(['trading/ChartToolbar.jsx', 'trading/StatsBar.jsx', 
                                   'trading/CandlestickChart.jsx', 'trading/ChartSkeleton.jsx',
                                   'trading/formatters.js'])
    
    # Analizza componenti
    components_dir = frontend_src / 'components'
    removed = 0
    
    if components_dir.exists():
        for comp_file in components_dir.rglob('*.jsx'):
            if comp_file.name not in essential_components:
                try:
                    comp_file.unlink()
                    print_ok(f"Rimosso componente: {comp_file.relative_to(frontend_src)}")
                    removed += 1
                except Exception as e:
                    print_error(f"Errore rimozione {comp_file}: {e}")
    
    print_info(f"Rimossi {removed} componenti frontend non necessari")

def create_minimal_structure():
    """Crea una struttura minimale pulita."""
    print_header("CREAZIONE STRUTTURA MINIMALE")
    
    # File di configurazione minimale
    minimal_files = {
        'requirements.txt': """requests==2.31.0
eth-account==0.9.0
pycryptodome==3.20.0
msgpack==1.0.7
python-dotenv==1.0.0
flask==3.0.0
flask-cors==4.0.0""",
        
        '.env.example': """# Hyperliquid Credentials
HYPERLIQUID_WALLET_ADDRESS=0xYourWalletAddressHere
HYPERLIQUID_PRIVATE_KEY=0xYourPrivateKeyHere

# OpenRouter API Key
OPENROUTER_API_KEY=sk-or-v1-YourOpenRouterAPIKeyHere

# Dashboard Security
DASHBOARD_API_KEY=hyperliquid123-super-secure-key-456
VITE_DASHBOARD_API_KEY=hyperliquid123-super-secure-key-456

# Trading Configuration
EXECUTION_MODE=paper
ENABLE_MAINNET_TRADING=false
TRADING_PAIRS=BTC,ETH,SOL

# Risk Management
MAX_DRAWDOWN_PCT=0.12
DAILY_NOTIONAL_LIMIT_USD=500
DEFAULT_SL_PCT=0.03
DEFAULT_TP_PCT=0.05

# API Server
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=5000
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/hyperliquid_bot.log""",
        
        'README_MINIMAL.md': """# Hyperliquid Trading Bot - Versione Minimale

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
- API: http://localhost:5000"""
    }
    
    for filename, content in minimal_files.items():
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print_ok(f"Creato: {filename}")

def main():
    """Funzione principale."""
    print(f"\n{GREEN}{BOLD}🤖 PULIZIA PROGETTO HYPERLIQUID TRADING BOT{RESET}")
    print(f"{YELLOW}Questo script rimuoverà file e directory non essenziali.{RESET}")
    
    if not get_confirmation("Vuoi procedere con la pulizia?"):
        print_info("Operazione annullata.")
        return
    
    # Analizza struttura
    analysis = analyze_project_structure()
    
    print_header("FILE DA RIMUOVERE")
    if analysis['files_to_remove']:
        print("File:")
        for f in sorted(analysis['files_to_remove']):
            print(f"  {RED}✗{RESET} {f}")
    
    if analysis['dirs_to_remove']:
        print("\nDirectory:")
        for d in sorted(analysis['dirs_to_remove']):
            print(f"  {RED}✗{RESET} {d}/")
    
    if not analysis['files_to_remove'] and not analysis['dirs_to_remove']:
        print_info("Nessun file non essenziale trovato.")
    
    if not get_confirmation("Confermi la rimozione?"):
        print_info("Operazione annullata.")
        return
    
    # Rimuovi file e directory
    removed, errors = remove_files_and_dirs(
        analysis['files_to_remove'], 
        analysis['dirs_to_remove']
    )
    
    # Pulisci frontend
    cleanup_frontend()
    
    # Crea struttura minimale
    create_minimal_structure()
    
    print_header("PULIZIA COMPLETATA")
    print_info(f"Rimossi {removed} elementi con {errors} errori")
    print_info("\nProgetto ora contiene solo i file essenziali:")
    print("  • Core del bot trading")
    print("  • API server")
    print("  • Frontend dashboard essenziale")
    print("  • File di configurazione minimale")
    
    print(f"\n{YELLOW}Next steps:{RESET}")
    print("1. Verifica che .env sia configurato correttamente")
    print("2. Testa con: python hyperliquid_bot_executable_orders.py --single-cycle")
    print("3. Avvia tutto con: python run_local.sh (se disponibile)")

if __name__ == "__main__":
    main()