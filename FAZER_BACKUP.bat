@echo off
set "data=%date:/=-%"
set "hora=%time::=-%"
set "hora=%hora: =0%"
set "pasta_backup=Backups\Backup_%data%_%hora%"

echo Criando backup em: %pasta_backup%
mkdir "%pasta_backup%"

echo Copiando Banco de Dados...
if exist "mala_express.db" (
    copy "mala_express.db" "%pasta_backup%\"
) else (
    echo AVISO: Banco de dados nao encontrado.
)

echo Copiando Imagens...
if exist "imagens_malas" (
    xcopy "imagens_malas" "%pasta_backup%\imagens_malas\" /E /I /Y /Q
)

echo.
echo ==========================================
echo      BACKUP REALIZADO COM SUCESSO!
echo ==========================================
echo Seus dados estao salvos na pasta Backups.
echo.
pause