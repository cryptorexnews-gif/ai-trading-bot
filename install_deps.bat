@echo off
echo ========================================
echo 🤖 INSTALLAZIONE DIPENDENZE WINDOWS
echo ========================================
echo.

echo 1. Installazione dipendenze Python...
pip install requests==2.31.0
pip install eth-account==0.11.0
pip install pycryptodome==3.20.0
pip install msgpack-python==0.5.6
pip install python-dotenv==1.0.0
pip install flask==3.0.3
pip install flask-cors==4.0.0
pip install pytest==8.2.0
pip install pytest-mock==3.14.0

echo.
echo 2. Installazione dipendenze Node.js...
echo    (Potrebbe richiedere permessi di amministratore)
echo.

REM Pulisci cache npm e installa con --force
npm cache clean --force
npm install --force

echo.
echo 3. Creazione directory logs...
mkdir logs 2>nul

echo.
echo ✅ INSTALLAZIONE COMPLETATA!
echo.
echo Per avviare il progetto:
echo   python api_server.py
echo   npm run dev
echo.
echo Per testare la configurazione:
echo   python test_local.py
echo.
pause