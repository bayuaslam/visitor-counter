$ErrorActionPreference = "Stop"
$logPath = "C:\visitor-counter\network-recovery.log"

function Write-RecoveryLog {
    param([string]$Message)
    Add-Content -LiteralPath $logPath -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Message)
}

try {
    Write-RecoveryLog "Memulai pemeriksaan jaringan setelah startup."

    for ($attempt = 0; $attempt -lt 12; $attempt++) {
        $wifi = Get-NetAdapter -Name "Wi-Fi 3" -ErrorAction SilentlyContinue
        if ($wifi -and $wifi.Status -eq "Up") { break }
        Start-Sleep -Seconds 5
    }

    Set-Service -Name SharedAccess -StartupType Automatic
    Restart-Service -Name SharedAccess -Force
    Start-Sleep -Seconds 3

    $sharedAddress = Get-NetIPAddress -InterfaceAlias "Ethernet" -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -eq "192.168.137.1" }

    if (-not $sharedAddress) {
        Write-RecoveryLog "IP sharing belum tersedia; memulai ulang adapter Ethernet."
        Restart-NetAdapter -Name "Ethernet" -Confirm:$false
        Start-Sleep -Seconds 3
        Restart-Service -Name SharedAccess -Force
    }

    $finalAddress = Get-NetIPAddress -InterfaceAlias "Ethernet" -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty IPAddress
    Write-RecoveryLog ("Pemulihan selesai. IP Ethernet: " + ($finalAddress -join ", "))

    $heartbeatPath = "C:\visitor-counter\counter_heartbeat"
    $counterActive = Test-Path -LiteralPath $heartbeatPath
    if ($counterActive) {
        $counterActive = (Get-Date) - (Get-Item -LiteralPath $heartbeatPath).LastWriteTime -lt (New-TimeSpan -Seconds 15)
    }

    if (-not $counterActive) {
        Write-RecoveryLog "Heartbeat counter berhenti; menjalankan visitor counter kembali."
        Start-Process `
            -FilePath "C:\visitor-counter\.venv\Scripts\pythonw.exe" `
            -ArgumentList "C:\visitor-counter\visitor_counter.py" `
            -WorkingDirectory "C:\visitor-counter" `
            -WindowStyle Hidden
    }
}
catch {
    Write-RecoveryLog ("GAGAL: " + $_.Exception.Message)
    exit 1
}
