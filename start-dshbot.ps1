# 启动 DSH 版 QQ 机器人：记忆服务 + DSH qqbot2 + 桥接 + 面板
$ErrorActionPreference = "Continue"

$botDir = $PSScriptRoot
$cfg = Get-Content (Join-Path $botDir "config.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$dshHome = [string]$cfg.dsh_home
$dshExe = [string]$cfg.dsh_exe
$py = [string]$cfg.bridge_python
$pyPanel = [string]$cfg.panel_python
$keyFile = [string]$cfg.deepseek_key_file
$cmemPort = ([uri]$cfg.cmem_base).Port
$dshPort = ([uri]$cfg.dsh_base).Port
$dshHost = ([uri]$cfg.dsh_base).Host
$panelPort = [int]$cfg.panel_port
$qqExe = [string]$cfg.qq_exe
$snowDir = [string]$cfg.snowluma_dir
$logDir = [string]$cfg.log_dir
if (-not $snowDir) { $snowDir = Join-Path (Split-Path $botDir -Parent) "SnowLuma" }
if (-not $logDir) { $logDir = Join-Path (Split-Path $botDir -Parent) "logs" }
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$svcDir = Join-Path $dshHome "remembers-service"
$svcPy = Join-Path $svcDir ".venv-win\Scripts\python.exe"
$svcData = Join-Path $dshHome "remembers-data"
$biliVenv = Join-Path $dshHome "bili-duty\.venv\Scripts"

# 让 DSH 里的 bili-scroll 用装了 bilibili_api 的 3.12 环境
$env:PATH = "$biliVenv;" + $env:PATH

# 确保 QQ 在跑（SnowLuma 需要 QQ 进程才能拉起 OneBot）
if (-not (Get-Process QQ -ErrorAction SilentlyContinue)) {
    if ($qqExe -and (Test-Path $qqExe)) {
        Write-Host "[dshbot] 启动 QQ 客户端..."
        Start-Process -FilePath $qqExe
        Start-Sleep -Seconds 15
    } else {
        Write-Host "[dshbot] 未配置 qq_exe，跳过启动 QQ"
    }
}

# 确保 SnowLuma 在跑
$snow = Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -like "*SnowLuma*index.mjs*" }
if (-not $snow) {
    Write-Host "[dshbot] 启动 SnowLuma..."
    $env:SNOWLUMA_ACCEPT_EULA = "1"
    $env:SNOWLUMA_ACCEPT_PRIVACY = "1"
    $snowExe = Join-Path $snowDir "node.exe"
    $snowScript = Join-Path $snowDir "index.mjs"
    if ((Test-Path $snowExe) -and (Test-Path $snowScript)) {
        Start-Process -FilePath $snowExe -ArgumentList $snowScript `
            -WorkingDirectory $snowDir `
            -RedirectStandardOutput (Join-Path $logDir "snowluma.out") `
            -RedirectStandardError (Join-Path $logDir "snowluma.err") -WindowStyle Hidden
        Start-Sleep -Seconds 10
    } else {
        Write-Host "[dshbot] SnowLuma 未找到：$snowDir"
    }
}

# 记忆服务
if (-not (Get-NetTCPConnection -LocalPort $cmemPort -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host "[dshbot] 启动记忆服务..."
    $env:CMEM_DATA_DIR = $svcData
    $env:CMEM_PORT = "$cmemPort"
    $env:CMEM_HOST = "127.0.0.1"
    $env:CMEM_LLM_BASE = "https://api.deepseek.com/v1"
    $env:CMEM_LLM_KEY = (Get-Content $keyFile -Raw).Trim()
    $env:CMEM_LLM_MODEL = "deepseek-chat"
    $env:CMEM_EXTRACT = "1"
    $env:CMEM_INJECT_PATH = "$dshHome\qq-inject.jsonl"
    Start-Process -FilePath $svcPy -ArgumentList "$svcDir\server.py" -WorkingDirectory $svcDir `
        -RedirectStandardOutput "$svcData\cmem.out" `
        -RedirectStandardError "$svcData\cmem.err" -WindowStyle Hidden
    Start-Sleep -Seconds 5
}

# DSH 实例（qqbot2）
if (-not (Get-NetTCPConnection -LocalPort $dshPort -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host "[dshbot] 启动 DSH qqbot2..."
    $env:DSH_HOME = $dshHome
    $env:DEEPSEEK_API_KEY = (Get-Content $keyFile -Raw).Trim()
    Start-Process -FilePath $dshExe `
        -ArgumentList "--profile", "qqbot2", "--no-open", "--host", "$dshHost", "--port", "$dshPort" `
        -RedirectStandardOutput "$dshHome\qqbot2.out" `
        -RedirectStandardError "$dshHome\qqbot2.err" `
        -WindowStyle Hidden
    for ($i = 0; $i -lt 120; $i++) {
        Start-Sleep -Seconds 1
        if (Get-NetTCPConnection -LocalPort $dshPort -State Listen -ErrorAction SilentlyContinue) { break }
    }
}

if (-not (Get-NetTCPConnection -LocalPort $dshPort -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host "[dshbot] DSH 实例没起来，看 $dshHome\qqbot2.err"
    exit 1
}
Write-Host "[dshbot] DSH 实例在 ${dshHost}:$dshPort"

# 桥接
$bridge = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*$botDir\bridge.py*" }
if (-not $bridge) {
    $env:DSH_HOME = $dshHome
    Start-Process -FilePath $py -ArgumentList "$botDir\bridge.py" -WorkingDirectory $botDir `
        -RedirectStandardOutput "$botDir\bridge.out" -RedirectStandardError "$botDir\bridge.err" -WindowStyle Hidden
    Write-Host "[dshbot] 桥接已启动"
} else {
    Write-Host "[dshbot] 桥接已在运行 (pid $($bridge.ProcessId))"
}

# 面板
if (-not (Get-NetTCPConnection -LocalPort $panelPort -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $pyPanel -ArgumentList "$botDir\panel.py" -WorkingDirectory $botDir `
        -RedirectStandardOutput "$botDir\panel.out" -RedirectStandardError "$botDir\panel.err" -WindowStyle Hidden
    Write-Host "[dshbot] 面板已启动: http://127.0.0.1:$panelPort/"
} else {
    Write-Host "[dshbot] 面板已在运行: http://127.0.0.1:$panelPort/"
}
