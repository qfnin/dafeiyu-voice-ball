#Requires -Version 5.1
# 预下载 Whisper 语音识别模型（faster-whisper，走 hf-mirror.com 国内镜像）
# 不装也能用：首次语音对话时 faster-whisper 会自动下载，只是第一次会慢。
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ruic = $env:RUIC_HOME
if (-not $ruic) { $ruic = Join-Path (Split-Path -Parent $repo) 'RuiC-2D' }
$py = Join-Path $ruic '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) { throw "没有找到 venv Python：$py。请先运行 scripts\setup.ps1" }

$env:HF_ENDPOINT = 'https://hf-mirror.com'
$env:HF_HOME = Join-Path $repo 'models\hf'
$env:HF_HUB_CACHE = Join-Path $repo 'models\hf\hub'

Write-Host "[models] 预下载 Whisper base 模型到 $repo\models\whisper ..."
& $py -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8', download_root=r'$repo\models\whisper'); print('Whisper base 就绪')"
