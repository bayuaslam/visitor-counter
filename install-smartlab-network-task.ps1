$ErrorActionPreference = "Stop"

$recoveryScript = "C:\visitor-counter\repair-smartlab-network.ps1"
if (-not (Test-Path -LiteralPath $recoveryScript)) {
    throw "Script pemulihan tidak ditemukan: $recoveryScript"
}

$taskAction = New-ScheduledTaskAction `
    -Execute "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$recoveryScript`""
$taskTrigger = New-ScheduledTaskTrigger -AtStartup
$taskPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 3)

Register-ScheduledTask `
    -TaskName "SmartLab Network Recovery" `
    -Action $taskAction `
    -Trigger $taskTrigger `
    -Principal $taskPrincipal `
    -Settings $taskSettings `
    -Description "Memulihkan Internet Connection Sharing Wi-Fi 3 ke Ethernet setelah Windows startup." `
    -Force | Out-Null

Set-Service -Name SharedAccess -StartupType Automatic
Start-ScheduledTask -TaskName "SmartLab Network Recovery"

Write-Host "SmartLab Network Recovery berhasil dipasang." -ForegroundColor Green
Start-Sleep -Seconds 2
