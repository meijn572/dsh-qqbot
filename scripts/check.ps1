# 每阶段固定检查：单元测试 + smoke
$ErrorActionPreference = "Stop"
$bot = Split-Path -Parent $PSScriptRoot
$cfg = Get-Content (Join-Path $bot "config.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$py = if ($cfg.bridge_python) { [string]$cfg.bridge_python } elseif ($env:DSHBOT_PYTHON) { $env:DSHBOT_PYTHON } else { "python" }
Set-Location $bot
$env:PYTHONPATH = $bot

Write-Host "== unit tests =="
& $py -m unittest discover -s (Join-Path $bot "tests") -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "== smoke =="
& $py (Join-Path $bot "scripts\smoke.py")
exit $LASTEXITCODE
