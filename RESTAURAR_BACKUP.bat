@echo off
REM Script para restaurar backup anterior
cd /d "%~dp0"

echo.
echo ============================================
echo  Restaurar Backup Anterior
echo ============================================
echo.

REM Copiar o backup mais antigo para restaurar
copy /y "backups\mala_express_20260603_225022.db" "mala_express_restored.db"

echo.
echo Backup restaurado como: mala_express_restored.db
echo.
echo Para usar este backup:
echo 1. Pare o sistema (feche a janela)
echo 2. Renomeie mala_express.db para mala_express_atual.db
echo 3. Renomeie mala_express_restored.db para mala_express.db
echo 4. Inicie o sistema novamente
echo.
pause
