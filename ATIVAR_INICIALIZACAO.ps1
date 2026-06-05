# ============================================
# MalaExpress - Ativar Inicialização Automática
# ============================================

$pastaScript = Split-Path -Parent $MyInvocation.MyCommand.Path
$pathScript = Join-Path $pastaScript "INICIAR_SISTEMA.bat"
$pathAtalho = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\MalaExpress.lnk"

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
} else {
    Write-Host ""
    Write-Host "ERRO! Verifique as permissoes."
    Write-Host ""
}

Read-Host "Pressione Enter para sair"
