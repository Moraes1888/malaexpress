# ============================================
# MalaExpress - Configurar Inicialização Automática
# ============================================

Write-Host ""
Write-Host "============================================"
Write-Host " MalaExpress - Inicializacao Automatica"
Write-Host "============================================"
Write-Host ""
Write-Host " 1 - Ativar inicializacao automatica"
Write-Host " 2 - Desativar inicializacao automatica"
Write-Host " 0 - Sair"
Write-Host ""
$escolha = Read-Host "Escolha uma opcao"

$pastaScript = Split-Path -Parent $MyInvocation.MyCommand.Path
$pathScript = Join-Path $pastaScript "INICIAR_SISTEMA.bat"
$pathAtalho = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\MalaExpress.lnk"

if ($escolha -eq "1") {
    Write-Host ""
    Write-Host "Configurando inicializacao automatica..."
    
    # Criar atalho usando WScript
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($pathAtalho)
    $Shortcut.TargetPath = $pathScript
    $Shortcut.WorkingDirectory = $pastaScript
    $Shortcut.Description = "MalaExpress - Controle de Malas"
    $Shortcut.WindowStyle = 1
    $Shortcut.Save()
    
    if (Test-Path $pathAtalho) {
        Write-Host ""
        Write-Host "SUCESSO! O MalaExpress iniciara automaticamente quando voce ligar o PC."
        Write-Host ""
        Write-Host "Dica: Para desativar, execute este script novamente e escolha opcao 2."
        Write-Host ""
    } else {
        Write-Host ""
        Write-Host "ERRO! Verifique as permissoes."
        Write-Host ""
    }
    Read-Host "Pressione Enter para sair"
}

elseif ($escolha -eq "2") {
    Write-Host ""
    Write-Host "Removendo inicializacao automatica..."
    Remove-Item -Path $pathAtalho -Force -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "Inicializacao automatica desativada."
    Write-Host ""
    Read-Host "Pressione Enter para sair"
}

elseif ($escolha -eq "0") {
    exit
}

else {
    Write-Host ""
    Write-Host "Opcao invalida!"
    Write-Host ""
}
