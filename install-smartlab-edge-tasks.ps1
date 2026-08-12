$ErrorActionPreference = "Stop"

$appDir = "C:\visitor-counter"
$pythonw = Join-Path $appDir ".venv\Scripts\pythonw.exe"
$counter = Join-Path $appDir "visitor_counter.py"
$syncAgent = Join-Path $appDir "edge_sync_agent.py"

foreach ($path in @($pythonw, $counter, $syncAgent)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "File tidak ditemukan: $path"
    }
}

$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

$counterAction = New-ScheduledTaskAction `
    -Execute $pythonw `
    -Argument "`"$counter`"" `
    -WorkingDirectory $appDir

$syncAction = New-ScheduledTaskAction `
    -Execute $pythonw `
    -Argument "`"$syncAgent`"" `
    -WorkingDirectory $appDir

Register-ScheduledTask `
    -TaskName "SmartLab Visitor Counter" `
    -Action $counterAction `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Menjalankan YOLO visitor counter dengan akun Windows pemilik kredensial DPAPI kamera." `
    -Force | Out-Null

Register-ScheduledTask `
    -TaskName "SmartLab Edge Sync" `
    -Action $syncAction `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Mengirim event visitor dan heartbeat ke server LabHub melalui HTTPS." `
    -Force | Out-Null

Start-ScheduledTask -TaskName "SmartLab Visitor Counter"
Start-ScheduledTask -TaskName "SmartLab Edge Sync"

Write-Host "SmartLab Visitor Counter dan Edge Sync berhasil dipasang untuk $userId." -ForegroundColor Green
Write-Host "Pastikan .env berisi LABHUB_SERVER_URL, LABHUB_EDGE_DEVICE_ID, dan LABHUB_EDGE_DEVICE_TOKEN." -ForegroundColor Yellow
