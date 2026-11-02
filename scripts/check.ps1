# 每阶段固定检查：单元测试 + smoke
$ErrorActionPreference = "Stop"
$bot = Split-Path -Parent $PSScriptRoot
$py = "D:\QQBot\AstrBot\.venv\Scripts\python.exe"
Set-Location $bot
$env:PYTHONPATH = $bot

Write-Host "== unit tests =="
& $py -m unittest discover -s (Join-Path $bot "tests") -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "== smoke =="
& $py (Join-Path $bot "scripts\smoke.py")
exit $LASTEXITCODE
