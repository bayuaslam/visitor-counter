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
    Write-RecoveryLog "Proses visitor counter tidak dijalankan sebagai SYSTEM; gunakan SmartLab Edge Tasks agar DPAPI kamera tetap memakai akun Windows pemilik kredensial."
}
catch {
    Write-RecoveryLog ("GAGAL: " + $_.Exception.Message)
    exit 1
}
