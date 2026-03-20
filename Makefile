.PHONY: install test run-backend run-frontend run-all clean

install:
	@echo "📦 Installazione dipendenze..."
	pip install -r requirements.txt
	npm install

test:
	@echo "🧪 Test configurazione..."
	python test_local.py

run-backend:
	@echo "🌐 Avvio backend API server..."
	python api_server.py

run-frontend:
	@echo "📊 Avvio frontend dashboard..."
	npm run dev

run-all:
	@echo "🚀 Avvio completo..."
	./run_local.sh

single-cycle:
	@echo "🔁 Esecuzione singolo ciclo..."
	python hyperliquid_bot_executable_orders.py --single-cycle

check-positions:
	@echo "📊 Controllo posizioni..."
	python check_current_positions.py

test-connection:
	@echo "🔗 Test connessione..."
	python scripts/test_connection.py

clean:
	@echo "🧹 Pulizia..."
	rm -rf __pycache__ */__pycache__ *.pyc
	rm -rf logs/*.log
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -delete

env-setup:
	@echo "⚙️  Setup ambiente..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "📋 File .env creato. Modifica con le tue chiavi."; \
	else \
		echo "✅ File .env già esistente."; \
	fi

help:
	@echo "🤖 Comandi disponibili:"
	@echo "  make install       - Installa tutte le dipendenze"
	@echo "  make test          - Testa la configurazione"
	@echo "  make run-backend   - Avvia solo il backend API"
	@echo "  make run-frontend  - Avvia solo il frontend"
	@echo "  make run-all       - Avvia tutto (backend + frontend)"
	@echo "  make single-cycle  - Esegue un singolo ciclo di trading"
	@echo "  make check-positions - Controlla posizioni correnti"
	@echo "  make test-connection - Test completo della connessione"
	@echo "  make clean         - Pulisce file temporanei"
	@echo "  make env-setup     - Crea file .env da template"
	@echo "  make help          - Mostra questa help"