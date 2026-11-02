# 停止 DSH 版 QQ 机器人（桥接 + DSH 实例）
$ErrorActionPreference = "Continue"

$botDir = $PSScriptRoot
$cfg = Get-Content (Join-Path $botDir "config.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$dshPort = ([uri]$cfg.dsh_base).Port

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*$(Join-Path $botDir 'bridge.py')*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "[dshbot] 已停桥接 $($_.ProcessId)" }

$conn = Get-NetTCPConnection -LocalPort $dshPort -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    Stop-Process -Id $conn.OwningProcess -Force
    Write-Host "[dshbot] 已停 DSH 实例 $($conn.OwningProcess)"
}

Write-Host "[dshbot] 已全部停止"
