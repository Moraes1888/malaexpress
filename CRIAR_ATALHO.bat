@echo off
chcp 65001 >nul
REM Script para criar atalho na Área de Trabalho
cd /d "%~dp0"

echo.
echo Criando atalho na Área de Trabalho...

REM Criar atalho usando VBScript
echo Set WshShell = CreateObject("WScript.Shell") > "%TEMP%\criar_atalho.vbs"
echo Desktop = WshShell.SpecialFolders("Desktop") >> "%TEMP%\criar_atalho.vbs"
echo SetShortcut = WshShell.CreateShortcut(Desktop ^& "\MalaExpress.lnk") >> "%TEMP%\criar_atalho.vbs"
echo Shortcut.TargetPath = "%WINDIR%\System32\cmd.exe" >> "%TEMP%\criar_atalho.vbs"
echo Shortcut.Arguments = "/k ""%~dp0INICIAR_SISTEMA.bat""" >> "%TEMP%\criar_atalho.vbs"
echo Shortcut.WorkingDirectory = "%~dp0" >> "%TEMP%\criar_atalho.vbs"
echo Shortcut.Description = "MalaExpress - Controle de Malas" >> "%TEMP%\criar_atalho.vbs"
echo Shortcut.Save() >> "%TEMP%\criar_atalho.vbs"

cscript //nologo "%TEMP%\criar_atalho.vbs"
del "%TEMP%\criar_atalho.vbs"

echo.
echo SUCESSO! Atalho criado na Área de Trabalho!
echo.
pause
