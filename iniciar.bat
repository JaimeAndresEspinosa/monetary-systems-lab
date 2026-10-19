@echo off
cd /d "%~dp0"
echo Instalando dependencias...
python -m pip install -q -r requirements.txt
echo Arrancando Monetary Systems Lab en http://localhost:8000
start "" http://localhost:8000
python -m uvicorn app:app --port 8000
