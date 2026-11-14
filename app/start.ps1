# 大肥鱼语音球 · 启动器
# 纯 ASCII 内容，避免 cmd/PowerShell 的中文编码问题
$ErrorActionPreference = 'SilentlyContinue'

$src = Split-Path -Parent $PSScriptRoot                                    # 仓库根目录（app/ 的上一级）
$ruic = $env:RUIC_HOME
if (-not $ruic) { $ruic = Join-Path (Split-Path -Parent $src) 'RuiC-2D' }  # 默认：仓库旁边的 RuiC-2D
$py = Join-Path $ruic '.venv\Scripts\pythonw.exe'

# 日志目录
$logDir = Join-Path $src 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
$log = Join-Path $logDir 'start.log'

function Log($m) {
  $line = "$(Get-Date -Format 'HH:mm:ss')  $m"
  Add-Content -Path $log -Value $line -Encoding UTF8
}

Log '=== start ==='

# 1) 已经在跑？把它显示出来
$running = @(Get-Process electron -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*RuiC*' -or $_.MainWindowTitle -like '*大肥鱼*' })
if ($running.Count -gt 0) {
  Log "already running: $($running.Count)"
  Add-Type @'
using System;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
'@
  foreach ($p in $running) {
    if ($p.MainWindowHandle -ne 0) {
      [W]::ShowWindow($p.MainWindowHandle, 9) | Out-Null
      [W]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
    }
  }
  exit 0
}

# 2) 语音桥
$up = $false
try {
  $r = Invoke-WebRequest 'http://127.0.0.1:8798/ping' -UseBasicParsing -TimeoutSec 2
  if ($r.StatusCode -eq 200) { $up = $true }
} catch {}
if (-not $up) {
  Log 'starting voice bridge'
  $env:HF_HOME = Join-Path $src 'models\hf'
  $env:HF_HUB_CACHE = Join-Path $src 'models\hf\hub'
  $env:HF_ENDPOINT = 'https://hf-mirror.com'
  $env:TMP = Join-Path $src 'cache\tmp'
  $env:TEMP = $env:TMP
  $env:PYTHONIOENCODING = 'utf-8'
  Start-Process -FilePath $py -ArgumentList "`"$src\app\voice_bridge.py`"" -WorkingDirectory $src -WindowStyle Hidden
  Start-Sleep -Seconds 4
}

# 3) 悬浮球
Log 'starting ball shell'
$env:ELECTRON_RUN_AS_NODE = ''
Start-Process -FilePath $py -ArgumentList "`"$src\app\launch.py`"" -WorkingDirectory $src -WindowStyle Hidden
Log 'done'
