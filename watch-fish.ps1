$ErrorActionPreference = "Continue"
$vbs = "D:\QQBot\dshbot\start-fish.vbs"
while ($true) {
    $missing = $false
    foreach ($port in 8081, 60773, 6080) {
        if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
            $missing = $true
            break
        }
    }
    if ($missing) {
        Start-Process -FilePath "C:\WINDOWS\System32\wscript.exe" -ArgumentList "`"$vbs`"" -WindowStyle Hidden
        Write-Output "[watch] $(Get-Date -Format 'HH:mm:ss') fish missing, start-fish.vbs launched"
    }
    Start-Sleep -Seconds 120
}
