#!/usr/bin/env node
/**
 * 大肥鱼语音球 · 插件侧管理进程
 *
 * 由 lib/index.js（DSH 宿主插件）拉起，职责：
 *   1. 首次运行自动配置环境：克隆 RuiC-2D → 建 venv → 装 Python 依赖 → 装 Electron
 *   2. 启动语音桥（voice_bridge.py：whisper 听 / LLM 答 / edge-tts 说）
 *   3. 启动悬浮球窗口（launch.py → Electron）
 *   4. 守护：子进程退出自动拉起；DSH 停插件时随 SIGTERM 全部退出
 *
 * 独立调试：node scripts/ball-manager.mjs --check   只检查前置条件，不启动
 *           RUIC_HOME=... node scripts/ball-manager.mjs --check
 */
import { spawn, execFileSync } from 'node:child_process';
import { appendFileSync, existsSync, mkdirSync, writeFileSync, copyFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import net from 'node:net';

const PKG = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const LOG = join(PKG, 'logs', 'plugin.log');
const MARKER = join(PKG, '.setup-done');
const DRY = process.argv.includes('--check');
const PY_DEPS = ['faster-whisper', 'edge-tts', 'sounddevice', 'numpy', 'Pillow', 'websocket-client'];
const RUIC = process.env.RUIC_HOME || join(PKG, 'RuiC-2D');
const PYW = join(RUIC, '.venv', 'Scripts', 'pythonw.exe');
const PYX = join(RUIC, '.venv', 'Scripts', 'python.exe');
const PYPI = ['-i', 'https://pypi.tuna.tsinghua.edu.cn/simple', '--quiet'];
const GIT_URLS = [
  'https://github.com/HRuiCcc/RuiC-2D.git',
  'https://gh-proxy.com/https://github.com/HRuiCcc/RuiC-2D.git',
];

function log(...parts) {
  const line = new Date().toLocaleTimeString('zh-CN', { hour12: false }) + '  ' + parts.join(' ');
  try { console.log(line); } catch { /* 无控制台 */ }
  try {
    mkdirSync(dirname(LOG), { recursive: true });
    appendFileSync(LOG, line + '\n');
  } catch { /* 磁盘不可写就放过 */ }
}

function have(cmd, args = ['--version']) {
  try { execFileSync(cmd, args, { windowsHide: true, stdio: 'ignore' }); return true; } catch { return false; }
}

function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(cmd, args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], ...opts });
    } catch (e) { log(`[spawn-err] ${cmd}: ${e.message}`); return resolve(-1); }
    child.stdout?.on('data', (d) => { const s = String(d).trim(); if (s) log(`[out] ${s.slice(0, 200)}`); });
    child.stderr?.on('data', (d) => { const s = String(d).trim(); if (s) log(`[err] ${s.slice(0, 200)}`); });
    child.on('exit', (code) => resolve(code ?? -1));
    child.on('error', (e) => { log(`[spawn-err] ${cmd}: ${e.message}`); resolve(-1); });
  });
}

function portInUse(port) {
  return new Promise((resolve) => {
    const sock = net.connect({ host: '127.0.0.1', port }, () => { sock.destroy(); resolve(true); });
    sock.on('error', () => resolve(false));
    sock.setTimeout(800, () => { sock.destroy(); resolve(false); });
  });
}

async function ensureSetup() {
  if (existsSync(MARKER)) { log('环境已配置过，跳过首次安装'); return true; }
  log('=== 首次运行：自动配置环境（约需几分钟，取决于网络） ===');
  const missing = [];
  for (const [cmd, why] of [['git', '克隆角色引擎 RuiC-2D'], ['node', '运行悬浮球 Electron'], ['python', '语音识别与合成']]) {
    if (have(cmd)) log(`前置 ${cmd} ✓`); else missing.push(`${cmd}（${why}）`);
  }
  if (missing.length) {
    log(`缺少前置工具：${missing.join('、')}。请安装 git + Node.js 20+ + Python 3.10+ 后重启 DSH。`);
    return false;
  }
  if (!existsSync(join(RUIC, 'server.mjs'))) {
    let cloned = false;
    for (const url of GIT_URLS) {
      log(`克隆角色引擎：${url}`);
      if (await run('git', ['clone', '--depth', '1', url, RUIC]) === 0) { cloned = true; break; }
    }
    if (!cloned || !existsSync(join(RUIC, 'server.mjs'))) { log('RuiC-2D 克隆失败，无法继续'); return false; }
  } else { log('RuiC-2D 已存在 ✓'); }
  if (!existsSync(PYX)) {
    log('创建 Python 虚拟环境');
    if (await run('python', ['-m', 'venv', join(RUIC, '.venv')]) !== 0) { log('venv 创建失败'); return false; }
  } else { log('Python venv 已存在 ✓'); }
  if (!existsSync(join(RUIC, 'requirements.txt'))) { log('RuiC-2D 目录不完整（缺 requirements.txt），删除该目录后重启 DSH 可重试'); return false; }
  log('安装 Python 依赖（RuiC-2D requirements + 语音球依赖，走清华镜像）');
  await run(PYX, ['-m', 'pip', 'install', ...PYPI, '-r', join(RUIC, 'requirements.txt')]);
  await run(PYX, ['-m', 'pip', 'install', ...PYPI, ...PY_DEPS]);
  if (!existsSync(join(PKG, 'shell', 'node_modules', 'electron', 'dist', 'electron.exe'))) {
    log('安装悬浮球依赖（npm ci，含 Electron 下载，几分钟）');
    await run('npm', ['ci'], { cwd: join(PKG, 'shell') });
    if (!existsSync(join(PKG, 'shell', 'node_modules', 'electron', 'dist', 'electron.exe'))) {
      log('npm ci 未产出 Electron，改用 npm install 重试');
      await run('npm', ['install'], { cwd: join(PKG, 'shell') });
    }
    if (!existsSync(join(PKG, 'shell', 'node_modules', 'electron', 'dist', 'electron.exe'))) {
      log('Electron 安装失败：悬浮球窗口将无法启动（语音桥仍可用）');
    } else { log('Electron 就绪 ✓'); }
  } else { log('Electron 已就绪 ✓'); }
  if (!existsSync(join(PKG, 'config.json'))) {
    try { copyFileSync(join(PKG, 'config.example.json'), join(PKG, 'config.json')); log('已生成默认 config.json'); } catch { /* 无关紧要 */ }
  }
  writeFileSync(MARKER, new Date().toISOString());
  log('=== 环境配置完成 ===');
  return true;
}

let bridgeProc = null;
let ballProc = null;
let bridgeRetries = 0;
let ballRetries = 0;
const MAX_RETRY = 5;

function childEnv() {
  return {
    ...process.env,
    RUIC_HOME: RUIC,
    HF_ENDPOINT: 'https://hf-mirror.com',
    HF_HOME: join(PKG, 'models', 'hf'),
    HF_HUB_CACHE: join(PKG, 'models', 'hf', 'hub'),
    TMP: join(PKG, 'cache', 'tmp'),
    TEMP: join(PKG, 'cache', 'tmp'),
    PYTHONIOENCODING: 'utf-8',
    ELECTRON_RUN_AS_NODE: '',
  };
}

function startBridge() {
  if (bridgeProc) return;
  if (!existsSync(PYW)) { log(`找不到 ${PYW}，语音桥无法启动`); return; }
  bridgeProc = spawn(PYW, [join(PKG, 'app', 'voice_bridge.py')], {
    cwd: PKG, env: childEnv(), windowsHide: true, stdio: 'ignore',
  });
  log(`语音桥已启动 pid=${bridgeProc.pid}`);
  bridgeProc.on('exit', (code) => {
    bridgeProc = null;
    if (shuttingDown) return;
    bridgeRetries += 1;
    if (bridgeRetries <= MAX_RETRY) {
      log(`语音桥退出 code=${code}，${5}s 后第 ${bridgeRetries} 次重启`);
      setTimeout(() => { if (!shuttingDown) { portInUse(8798).then((used) => { if (!used) startBridge(); else log('8798 已被占用，不再重启语音桥'); }); } }, 5000);
    } else { log('语音桥反复退出，停止重启（查看 logs/bridge.log 排查）'); }
  });
}

function startBall() {
  if (ballProc) return;
  if (!existsSync(join(PKG, 'shell', 'node_modules', 'electron', 'dist', 'electron.exe'))) {
    log('Electron 未就绪，悬浮球窗口跳过（等依赖装好后重启 DSH 再试）');
    return;
  }
  ballProc = spawn(PY, [join(PKG, 'app', 'launch.py')], {
    cwd: PKG, env: childEnv(), windowsHide: true, stdio: 'ignore',
  });
  log(`悬浮球已启动 pid=${ballProc.pid}`);
  ballProc.on('exit', (code) => {
    ballProc = null;
    if (shuttingDown) return;
    ballRetries += 1;
    if (ballRetries <= MAX_RETRY) {
      log(`悬浮球进程退出 code=${code}，${8}s 后第 ${ballRetries} 次重启`);
      setTimeout(() => { if (!shuttingDown) startBall(); }, 8000);
    } else { log('悬浮球反复退出，停止重启（查看 logs/launch.log 排查）'); }
  });
}

let shuttingDown = false;
function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  log('收到退出信号，关闭语音桥与悬浮球');
  try { bridgeProc?.kill(); } catch { /* 已退出 */ }
  try { ballProc?.kill(); } catch { /* 已退出 */ }
  setTimeout(() => process.exit(0), 1200);
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

async function main() {
  log(`=== 大肥鱼语音球管理进程启动（pkg=${PKG}） ===`);
  if (DRY) {
    log('--check 模式：只检查前置条件，不启动');
    for (const [cmd, why] of [['git', '克隆角色引擎'], ['node', '运行悬浮球'], ['python', '语音识别/合成']]) {
      log(`${cmd}（${why}）: ${have(cmd) ? '✓' : '✗ 缺失'}`);
    }
    log(`RUIC_HOME: ${RUIC} → ${existsSync(join(RUIC, 'server.mjs')) ? '✓ 已就绪' : '将克隆'}`);
    log(`venv python: ${existsSync(PYX) ? '✓' : '将创建'}`);
    log(`Electron: ${existsSync(join(PKG, 'shell', 'node_modules', 'electron', 'dist', 'electron.exe')) ? '✓' : '将 npm 安装'}`);
    log(`语音桥端口 8798: ${await portInUse(8798) ? '占用中（可能有实例在跑）' : '空闲'}`);
    log('--check 完成');
    return;
  }
  mkdirSync(join(PKG, 'logs'), { recursive: true });
  mkdirSync(join(PKG, 'cache', 'tmp'), { recursive: true });

  const ok = await ensureSetup();
  if (!ok) { log('自动配置未完成，管理进程退出（修复前置条件后重启 DSH 重试）'); process.exit(1); }

  if (await portInUse(8798)) {
    log('8798 端口已有语音桥在跑，不重复启动');
  } else { startBridge(); }

  // 等 Electron 页面起来后再开窗口（launch.py 自己会等 RuiC-2D 服务）
  await new Promise((r) => setTimeout(r, 3000));
  startBall();

  // 心跳：每 60s 确认语音桥活着（崩了由 exit 回调重启，这里兜底端口丢失场景）
  setInterval(() => {
    if (shuttingDown) return;
    portInUse(8798).then((used) => { if (!used && !bridgeProc && bridgeRetries <= MAX_RETRY) { log('心跳发现语音桥不在，尝试重启'); startBridge(); } });
  }, 60000);
}

main().catch((e) => { log(`管理进程异常退出: ${e?.message ?? e}`); process.exit(1); });
