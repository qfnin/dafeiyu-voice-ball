#Requires -Version 5.1
# 大肥鱼语音球 · 一键安装
#
# 做四件事：
#   1. 把角色引擎 RuiC-2D 克隆到本仓库旁边（或 RUIC_HOME 指定的位置）
#   2. 在 RuiC-2D 里建 Python venv，装齐两边的 Python 依赖
#   3. npm install 装悬浮球的 Electron 依赖（npm 缓存已由 shell/.npmrc 指到仓库内）
#   4. （可选）预下载 Whisper 语音识别模型
#
# 全程只写「本仓库目录 + RuiC-2D 目录」，不往 C 盘装任何东西。
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # scripts/ 的上一级 = 仓库根目录
$ruic = $env:RUIC_HOME
if (-not $ruic) { $ruic = Join-Path (Split-Path -Parent $repo) 'RuiC-2D' }

$BALL_PY_DEPS = @('faster-whisper', 'edge-tts', 'sounddevice', 'numpy', 'Pillow', 'websocket-client')

function Step($m) { Write-Host "[setup] $m" -ForegroundColor Cyan }

# ---------- 0. 前置检查 ----------
Step '检查前置工具（git / node >= 20 / python >= 3.10）'
foreach ($tool in 'git', 'node', 'python') {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
    throw "没有找到 $tool。请先安装后再运行本脚本。"
  }
}
$nodeVer = (node --version) -replace 'v', ''
if ([version]($nodeVer.Split('.')[0] + '.0') -lt [version]'20.0') { throw "Node.js 需要 >= 20，当前 $nodeVer" }
Write-Host "  git / node $nodeVer / python $((python --version) 2>&1) 就绪"

# ---------- 1. RuiC-2D ----------
if (Test-Path (Join-Path $ruic 'server.mjs')) {
  Step "RuiC-2D 已存在：$ruic"
} else {
  Step "克隆角色引擎 RuiC-2D 到 $ruic"
  git clone https://github.com/HRuiCcc/RuiC-2D.git $ruic
}

# ---------- 2. Python venv + 依赖 ----------
$venvPy = Join-Path $ruic '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
  Step "创建 Python venv：$ruic\.venv"
  python -m venv (Join-Path $ruic '.venv')
}

Step '安装 Python 依赖（RuiC-2D requirements + 悬浮球依赖，走国内镜像）'
& $venvPy -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r (Join-Path $ruic 'requirements.txt') --quiet
& $venvPy -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple @BALL_PY_DEPS --quiet

# ---------- 3. Electron 依赖 ----------
Step '安装悬浮球 Electron 依赖（shell/）'
Push-Location (Join-Path $repo 'shell')
try {
  npm ci 2>$null
  if ($LASTEXITCODE -ne 0) { npm install }
} finally { Pop-Location }

# ---------- 4. 模型（可选） ----------
$answer = Read-Host '[setup] 现在预下载 Whisper base 语音识别模型吗？约 150MB，首次对话会更快 (y/N)'
if ($answer -match '^[yY]') {
  & (Join-Path $PSScriptRoot 'prepare-models.ps1')
}

Write-Host ''
Write-Host '[setup] 完成！' -ForegroundColor Green
Write-Host '  - 双击仓库里的 大肥鱼语音球.vbs 即可启动'
Write-Host '  - 回答后端默认 ollama（本地、免费）；想用 DeepSeek 官方 API，把 config.json 里的 llm_backend 改成 deepseek，并设置环境变量 DEEPSEEK_API_KEY'
Write-Host '  - 配置项说明见 README.md'
