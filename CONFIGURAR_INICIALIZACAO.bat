@echo off
chcp 65001 >nul
REM ============================================
REM Script para configurar inicialização automática
REM do MalaExpress com o Windows (via Agendador)
REM ============================================

cd /d "%~dp0"

echo.
echo ============================================
echo  MalaExpress - Inicialização Automática
echo ============================================
echo.
echo  1 - Ativar inicialização automática
echo  2 - Desativar inicialização automática
echo  0 - Sair
echo.
set /p escolha="Escolha uma opção: "

if "%escolha%"=="1" goto instalar
if "%escolha%"=="2" goto desinstalar
if "%escolha%"=="0" goto fim

echo Opção inválida!
goto fim

:instalar
echo.
echo Configurando inicialização automática...
REM Criar tarefa no Agendador de Tarefas do Windows
schtasks /create /tn "MalaExpress" /tr "\"%CD%INICIAR_SISTEMA.bat\"" /sc onlogon /rl limited /f
if %errorlevel%==0 (
    echo.
    echo SUCESSO! O MalaExpress iniciara automaticamente quando voce ligar o PC.
    echo.
) else (
    echo.
    echo ERRO! Verifique se voce tem permissao de administrador.
    echo.
)
pause
goto fim

:desinstalar
echo.
echo Removendo inicialização automática...
schtasks /delete /tn "MalaExpress" /f 2>nul
if %errorlevel%==0 (
    echo.
    echo A inicialização automática foi desativada.
    echo.
) else (
    echo.
    echo A inicialização automática já estava desativada.
    echo.
)
pause
goto fim

:fim
