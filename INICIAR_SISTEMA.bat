@echo off
TITLE MalaExpress - Sistema de Controle
echo Iniciando o sistema MalaExpress...
echo Por favor, aguarde enquanto o navegador abre...
cd /d "%~dp0"
call .venv\Scripts\activate
python -c "import database as db; ok, msg = db.backup_db(); print(msg)"
echo.
streamlit run app.py
pause