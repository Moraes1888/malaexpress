# ============================================
# MalaExpress - Criar Atalho na Área de Trabalho
# ============================================

$pastaScript = Split-Path -Parent $MyInvocation.MyCommand.Path
$atalhoPath = [Environment]::GetFolderPath('Desktop') + "\MalaExpress.lnk"
$scriptPath = Join-Path $pastaScript "INICIAR_SISTEMA.bat"

Write-Host ""
Write-Host "Criando atalho na Área de Trabalho..."

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($atalhoPath)
$Shortcut.TargetPath = $scriptPath
$Shortcut.WorkingDirectory = $pastaScript
$Shortcut.Description = "MalaExpress - Controle de Malas"
$Shortcut.WindowStyle = 1  # Normal window
$Shortcut.Save()

if (Test-Path $atalhoPath) {
    Write-Host ""
    Write-Host "SUCESSO! Atalho criado na Área de Trabalho!"
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "ERRO ao criar atalho."
    Write-Host ""
}

Read-Host "Pressione Enter para sair"
