@echo off
TITLE Configurar Nome MalaExpress
color 1F
echo.
echo ========================================================
echo   CONFIGURACAO DE NOME PERSONALIZADO (MalaExpress)
echo ========================================================
echo.
echo Este script ira configurar o Windows para aceitar o nome
echo "malaexpress" no lugar de "localhost".
echo.
echo Voce podera acessar o sistema por: http://malaexpress:8501
echo.
echo Para isso, precisamos de permissao de ADMINISTRADOR.
echo Uma janela azul do PowerShell abrira rapidamente.
echo Se o Windows pedir permissao, clique em SIM.
echo.
pause
echo.
echo Configurando...
powershell -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command \"$h = ''$env:windir\System32\drivers\etc\hosts''; $c = Get-Content $h; if (-not ($c -match ''malaexpress'')) { Add-Content -Path $h -Value ''`r`n127.0.0.1 malaexpress'' }; Write-Host ''Configurado com Sucesso!''\"'"
echo.
echo ========================================================
echo                 CONCLUIDO!
echo ========================================================
echo Agora, quando iniciar o sistema, voce pode digitar
echo http://malaexpress:8501 no seu navegador.
echo.
pause