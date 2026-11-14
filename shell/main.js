// RuiC-2D 桌面悬浮球：Electron 外壳（自己拥有窗口，不依赖系统 Edge，也不受 UIPI 限制）
// 透明无边框置顶小窗 + 系统右键菜单 + edge-tts 说话 + 位置记忆 + 开机自启
// 缓存/用户数据/日志/音频全部写在项目目录（D 盘）。
const { app, BrowserWindow, Menu, ipcMain, screen, clipboard } = require('electron');
const path = require('path');
const fs = require('fs');
const net = require('net');
const { spawn, execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const SHELL = __dirname;
const CFG_PATH = path.join(ROOT, 'config.json');
const LOG_PATH = path.join(ROOT, 'logs', 'shell.log');
const TTS_DIR = path.join(ROOT, 'tts');
const SITE = 'http://127.0.0.1:8796';
const RUIC = process.env.RUIC_HOME || path.resolve(ROOT, '..', 'RuiC-2D');   // 优先 RUIC_HOME 环境变量，否则用仓库旁边的 RuiC-2D
const PYTHON = path.join(RUIC, '.venv', 'Scripts', 'python.exe');
const ELECTRON_EXE = path.join(SHELL, 'node_modules', 'electron', 'dist', 'electron.exe');
const STARTUP_KEY = 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run';
const STARTUP_NAME = 'RuiC2DBall';
const VOICE_PORT = 8798;          // 语音桥（识别/对话/合成）
const PY = path.join(RUIC, '.venv', 'Scripts', 'pythonw.exe');
let voiceProc = null;

const DEFAULTS = {
  project: 'da-fei-yu-1',
  diameter: 340,
  x: null,
  y: null,
  voice: 'zh-CN-XiaoxiaoNeural',
  rate: '+10%',
  pitch: '+8Hz',
  zoom: 1.52,
  anchorY: 0.46,
  max_chars: 300,
  topmost: true,
  hardCircle: false,  // true=再用圆形窗口区域裁一刀硬边；false=只靠透明+页面里的圆（边缘更细腻）
};

fs.mkdirSync(path.join(ROOT, 'logs'), { recursive: true });
fs.mkdirSync(TTS_DIR, { recursive: true });
fs.mkdirSync(path.join(ROOT, 'cache', 'tmp'), { recursive: true });
app.setPath('userData', path.join(ROOT, 'cache', 'electron-userdata'));
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('remote-debugging-port', '9334');   // 仅本机；用来诊断页面尺寸/渲染
// 不要强制 device-scale-factor：它会让「页面坐标」和「Win32 窗口坐标」错位，
// 按钮就跑到窗口外面点不到了。让 Electron 跟系统 DPI 走，两者自然一致。
process.env.TMP = process.env.TMP || path.join(ROOT, 'cache', 'tmp');
process.env.TEMP = process.env.TEMP || path.join(ROOT, 'cache', 'tmp');

function log(...parts) {
  const line = `${new Date().toLocaleTimeString()}  ${parts.join(' ')}`;
  try { fs.appendFileSync(LOG_PATH, line + '\n'); } catch {}
  console.log(line);
}

function loadConfig() {
  const cfg = { ...DEFAULTS };
  try { Object.assign(cfg, JSON.parse(fs.readFileSync(CFG_PATH, 'utf8').replace(/^\uFEFF/, ''))); }
  catch (e) { if (e.code !== 'ENOENT') log('配置读取失败，用默认值：', e.message); }
  return cfg;
}
function saveConfig(cfg) {
  try { fs.writeFileSync(CFG_PATH, JSON.stringify(cfg, null, 2), 'utf8'); } catch (e) { log('配置保存失败：', e.message); }
}

const cfg = loadConfig();
let win = null;
let inputWin = null;
let dragTimer = null;

function portOpen() {
  return new Promise((resolve) => {
    const sock = net.connect({ host: '127.0.0.1', port: 8796 }, () => { sock.destroy(); resolve(true); });
    sock.on('error', () => resolve(false));
    sock.setTimeout(500, () => { sock.destroy(); resolve(false); });
  });
}

async function ensureServer() {
  if (await portOpen()) return true;
  try {
    spawn('node', ['server.mjs'], {
      cwd: RUIC, env: { ...process.env, YOUXING_PYTHON: PYTHON },
      detached: true, stdio: 'ignore', windowsHide: true,
    }).unref();
    log('已拉起 RuiC-2D 服务');
  } catch (e) { log('拉起服务失败：', e.message); }
  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 500));
    if (await portOpen()) return true;
  }
  return false;
}

function synth(text) {
  return new Promise((resolve) => {
    const clean = String(text || '').trim().slice(0, cfg.max_chars);
    if (!clean) return resolve(null);
    const out = path.join(TTS_DIR, 'last.mp3');
    const child = spawn(PYTHON, ['-m', 'edge_tts', '--voice', cfg.voice, '--rate', cfg.rate,
      '--pitch', cfg.pitch, '--text', clean, '--write-media', out], { cwd: ROOT, windowsHide: true });
    let err = '';
    child.stderr.on('data', (d) => { err += d.toString(); });
    child.on('exit', (code) => {
      if (code !== 0) { log('合成失败：', err.slice(-200)); return resolve(null); }
      try {
        const buf = fs.readFileSync(out);
        log(`合成 ${clean.length} 字 -> ${buf.length} 字节`);
        resolve('data:audio/mpeg;base64,' + buf.toString('base64'));
      } catch (e) { log('读取合成结果失败：', e.message); resolve(null); }
    });
  });
}

async function speak(text) {
  const url = await synth(text);
  if (url && win && !win.isDestroyed()) win.webContents.send('speak', url);
  return url;
}

function pageUrl(forceStatic) {
  const staticPart = (forceStatic || cfg.staticMode) ? '&static=1' : '';
  // 不给 zoom，让页面按 rig 自动构图（窗口多大都框得一样）
  return `${SITE}/pet.html?project=${cfg.project}&anchorY=${cfg.anchorY}${staticPart}`;
}

function createBall() {
  const opaque = !!process.env.BALL_OPAQUE;      // 透明窗口在某些会话里根本画不出来，就用不透明窗+圆形区域
  const forceStatic = !!process.env.BALL_STATIC; // 强制页面走静态立绘模式
  // 位置：配置里有就用；没有就贴到主屏右上角，别跑到屏幕外面去
  let px = cfg.x, py = cfg.y;
  if (px === null || py === null) {
    const area = screen.getPrimaryDisplay().workArea;
    px = Math.round(area.x + area.width - cfg.diameter - 60);
    py = Math.round(area.y + 80);
    cfg.x = px; cfg.y = py;
    log('首次启动，默认放到右上角：', px, py);
  }
  win = new BrowserWindow({
    width: cfg.diameter,
    height: cfg.diameter,
    x: px,
    y: py,
    frame: false,
    transparent: !opaque,
    resizable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    hasShadow: false,
    alwaysOnTop: cfg.topmost !== false,
    backgroundColor: opaque ? '#12162a' : '#00000000',
    webPreferences: {
      preload: path.join(SHELL, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });
  win.setAlwaysOnTop(cfg.topmost !== false, 'screen-saver');
  // 窗口尺寸必须和页面一致：之前出现「窗口 240 但页面 360」的错位，
  // 导致按钮跑到窗口外面点不到。这里显式锁死内容尺寸。
  win.setContentSize(cfg.diameter, cfg.diameter);
  setTimeout(() => {
    try {
      const [w, h] = win.getContentSize();
      log(`窗口内容尺寸 = ${w}x${h}（配置 ${cfg.diameter}）`);
      if (w !== cfg.diameter || h !== cfg.diameter) {
        win.setContentSize(cfg.diameter, cfg.diameter);
        log('尺寸不一致，已强制校正');
      }
    } catch (e) { log('校正尺寸失败：', e.message); }
  }, 800);
  if (opaque) {
    // 不透明窗 + 圆形窗口区域：我们自己拥有窗口，普通权限也能裁
    setTimeout(() => {
      try {
        const hwnd = readHwnd(win.getNativeWindowHandle());
        const b = win.getBounds();
        const scale = screen.getPrimaryDisplay().scaleFactor || 1;   // 区域要用物理像素
        log('裁圆 hwnd=', hwnd, 'size=', Math.round(b.width * scale), 'scale=', scale);
        hardCircle(hwnd, Math.round(b.width * scale), Math.round(b.height * scale));
      } catch (e) { log('裁圆失败：', e.message); }
    }, 1500);
  }
  win.loadURL(pageUrl(forceStatic));
  win.webContents.on('did-finish-load', () => log('页面加载完成'));
  win.webContents.on('did-fail-load', (_e, code, desc) => log('页面加载失败', code, desc));
  win.on('moved', () => {
    const [x, y] = win.getPosition();
    cfg.x = x; cfg.y = y; saveConfig(cfg);
  });
  win.on('closed', () => { win = null; });
  return win;
}

// Electron 的 getNativeWindowHandle() 在新版返回 Uint8Array 而不是 Buffer，这里统一处理
function readHwnd(raw) {
  try {
    const b = Buffer.isBuffer(raw) ? raw : Buffer.from(raw);
    if (b.length >= 8) return b.readBigUInt64LE(0).toString();
    if (b.length >= 4) return String(b.readUInt32LE(0));
  } catch (e) { log('读窗口句柄失败：', e.message); }
  return null;
}

// 用 PowerShell 的 Add-Type 太绕，这里直接用 ffi 式的 node 调 user32 不现实；
// 于是让一个短命的 python 进程负责给窗口设区域（同进程权限，能改自己的窗口）。
function hardCircle(hwnd, w, h) {
  if (!hwnd) return log('拿不到窗口句柄，跳过裁圆');
  const script = `
import ctypes, sys, time
from ctypes import wintypes
u=ctypes.WinDLL('user32', use_last_error=True); g=ctypes.WinDLL('gdi32')
u.SetWindowRgn.argtypes=[wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
h=int(sys.argv[1]); w=int(sys.argv[2]); h=int(sys.argv[3])
rgn=g.CreateEllipticRgn(0,0,w+1,h+1)
ok=u.SetWindowRgn(h, rgn, True)
print('set region', bool(ok))
`;
  const tmp = path.join(ROOT, 'cache', 'tmp', 'circle.py');
  fs.writeFileSync(tmp, script, 'utf8');
  spawn(PYTHON, [tmp, hwnd, String(w), String(h)], { windowsHide: true, stdio: 'ignore' });
}

// ---------------------------------------------------------------- 语音桥
function voiceAlive() {
  return new Promise((resolve) => {
    const sock = net.connect({ host: '127.0.0.1', port: VOICE_PORT }, () => { sock.destroy(); resolve(true); });
    sock.on('error', () => resolve(false));
    sock.setTimeout(600, () => { sock.destroy(); resolve(false); });
  });
}

async function ensureVoiceBridge() {
  if (await voiceAlive()) { log('语音桥已在运行'); return true; }
  try {
    voiceProc = spawn(PY, [path.join(ROOT, 'app', 'voice_bridge.py')], {
      cwd: ROOT,
      env: {
        ...process.env,
        HF_HOME: path.join(ROOT, 'models', 'hf'),
        HF_HUB_CACHE: path.join(ROOT, 'models', 'hf', 'hub'),
        TMP: path.join(ROOT, 'cache', 'tmp'),
        TEMP: path.join(ROOT, 'cache', 'tmp'),
        PYTHONIOENCODING: 'utf-8',
      },
      windowsHide: true, stdio: 'ignore', detached: false,
    });
    log('已启动语音桥进程');
  } catch (e) {
    log('启动语音桥失败：', e.message);
    return false;
  }
  for (let i = 0; i < 60; i++) {          // Whisper 首次加载要下载/读模型，给足 30 秒
    await new Promise((r) => setTimeout(r, 500));
    if (await voiceAlive()) { log('语音桥就绪'); return true; }
  }
  log('语音桥启动超时（球仍可用，只是暂时不能语音对话）');
  return false;
}

function voicePost(pathname, body) {
  return new Promise((resolve) => {
    const data = Buffer.from(JSON.stringify(body || {}), 'utf8');
    const req = require('http').request({
      host: '127.0.0.1', port: VOICE_PORT, path: pathname, method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': data.length },
      timeout: 180000,
    }, (res) => {
      let buf = '';
      res.setEncoding('utf8');
      res.on('data', (d) => { buf += d; });
      res.on('end', () => {
        try { resolve(JSON.parse(buf)); } catch (e) { resolve({ ok: false, why: '解析失败' }); }
      });
    });
    req.on('error', (e) => resolve({ ok: false, why: e.message }));
    req.on('timeout', () => { req.destroy(); resolve({ ok: false, why: '超时' }); });
    req.write(data);
    req.end();
  });
}

// 开始/停止通话（像打电话：接通知后一直聊，挂断才停）
let callTimer = null;
let onCall = false;

function voiceGet(pathname) {
  return new Promise((resolve) => {
    const req = require('http').get({
      host: '127.0.0.1', port: VOICE_PORT, path: pathname, timeout: 5000,
    }, (res) => {
      let buf = '';
      res.setEncoding('utf8');
      res.on('data', (d) => { buf += d; });
      res.on('end', () => { try { resolve(JSON.parse(buf)); } catch { resolve({}); } });
    });
    req.on('error', () => resolve({}));
    req.on('timeout', () => { req.destroy(); resolve({}); });
  });
}

async function startCall() {
  if (!win) { log('[通话] 没有窗口，无法接通'); return; }
  if (onCall) { log('[通话] 已经在通话中，忽略重复接通'); return; }
  onCall = true;
  log('[通话] 接通');
  win.webContents.send('voice-state', { state: 'listening', onCall: true });
  const r = await voicePost('/call/start', {});
  log('[通话] 后端:', JSON.stringify(r));

  // 持续轮询：状态 + 新回答
  if (callTimer) clearInterval(callTimer);
  callTimer = setInterval(async () => {
    if (!onCall) return;
    const s = await voiceGet('/status');
    if (s && s.phase) {
      win.webContents.send('voice-state', {
        state: s.phase === 'idle_wait' ? 'listening' : s.phase,
        text: s.last_text || '',
        turns: s.turns || 0,
        onCall: true,
      });
    }
    const next = await voiceGet('/next');
    if (next && next.url) {
      log('[通话] 收到回答:', (next.reply || '').slice(0, 30));
      win.webContents.send('speak', next.url);
    }
  }, 700);
}

async function stopCall() {
  if (!win) return;
  onCall = false;
  if (callTimer) { clearInterval(callTimer); callTimer = null; }
  log('[通话] 挂断');
  await voicePost('/call/stop', {});
  win.webContents.send('voice-state', { state: 'idle' });
  win.webContents.send('stop');
}

function openInput() {
  log('[输入框] 打开');
  if (inputWin && !inputWin.isDestroyed()) { inputWin.focus(); return; }
  inputWin = new BrowserWindow({
    width: 460, height: 170, resizable: false, alwaysOnTop: true, skipTaskbar: true,
    title: '跟大肥鱼说话', backgroundColor: '#141a2e', frame: true,
    webPreferences: { preload: path.join(SHELL, 'preload_input.js'), contextIsolation: true },
  });
  inputWin.setMenu(null);
  inputWin.loadFile(path.join(SHELL, 'input.html'));
  inputWin.webContents.on('did-finish-load', () => log('[输入框] 已加载'));
  inputWin.webContents.on('console-message', (_e, level, message) => log('[输入框页面]', message));
  inputWin.webContents.on('before-input-event', (_e, input) => {
    if (input.type === 'keyDown') log('[输入框按键]', input.key);
  });
  inputWin.on('closed', () => { inputWin = null; log('[输入框] 已关闭'); });
}

function startupEnabled() {
  try { return execFileSync('reg', ['query', STARTUP_KEY, '/v', STARTUP_NAME], { encoding: 'utf8', windowsHide: true }).includes(STARTUP_NAME); }
  catch { return false; }
}
function setStartup(on) {
  try {
    if (on) execFileSync('reg', ['add', STARTUP_KEY, '/v', STARTUP_NAME, '/t', 'REG_SZ', '/d', `"${ELECTRON_EXE}" "${SHELL}"`, '/f'], { windowsHide: true });
    else execFileSync('reg', ['delete', STARTUP_KEY, '/v', STARTUP_NAME, '/f'], { windowsHide: true });
  } catch (e) { log('写开机自启失败：', e.message); }
  log('开机自启 ->', startupEnabled());
}

function buildMenu() {
  const items = [
    { label: '接通（开始通话）', click: () => { log('[菜单] 接通'); startCall(); } },
    { label: '挂断', click: () => { log('[菜单] 挂断'); stopCall(); } },
    { type: 'separator' },
    { label: '朗读剪贴板', click: () => { log('[菜单] 朗读剪贴板'); speak(clipboard.readText()); } },
    { label: '输入文字说话…', click: () => { log('[菜单] 输入文字说话'); openInput(); } },
    { label: '停止说话', click: () => { log('[菜单] 停止说话'); win && win.webContents.send('stop'); } },
    { type: 'separator' },
    {
      label: '窗口置顶', type: 'checkbox', checked: cfg.topmost !== false,
      click: (item) => {
        log('[菜单] 窗口置顶 ->', item.checked);
        cfg.topmost = item.checked; saveConfig(cfg);
        if (win) win.setAlwaysOnTop(item.checked, 'screen-saver');
      },
    },
    {
      label: '开机自启', type: 'checkbox', checked: startupEnabled(),
      click: (item) => { log('[菜单] 开机自启 ->', item.checked); setStartup(item.checked); },
    },
    { label: '重新载入角色', click: () => { log('[菜单] 重新载入'); win && win.loadURL(pageUrl()); } },
    { type: 'separator' },
    { label: '退出悬浮球', click: () => { log('[菜单] 退出'); app.quit(); } },
  ];
  log('菜单项:', items.filter((i) => i.label).map((i, n) => `${n + 1}.${i.label}`).join(' '));
  return Menu.buildFromTemplate(items);
}

// 拖动：优先用 Electron 原生 app-region 拖动（页面里 #ball 设了 -webkit-app-region: drag）。
// 这里的定时器方案只在原生拖动不可用时作为兜底，而且必须能被可靠地停掉。
function startDrag() {
  stopDrag();
  const start = screen.getCursorScreenPoint();
  const [wx, wy] = win.getPosition();
  const started = Date.now();
  dragTimer = setInterval(() => {
    if (!win || win.isDestroyed()) return stopDrag();
    if (Date.now() - started > 15000) return stopDrag();   // 兜底：最长 15 秒
    const p = screen.getCursorScreenPoint();
    win.setPosition(wx + (p.x - start.x), wy + (p.y - start.y));
  }, 16);
}
function stopDrag() { if (dragTimer) clearInterval(dragTimer); dragTimer = null; }

// 窗口失焦 / 鼠标离开窗口时，也强制停掉拖动（防止球一直跟着光标）
app.on('browser-window-blur', () => stopDrag());

ipcMain.on('drag-start', startDrag);
ipcMain.on('drag-end', stopDrag);
ipcMain.on('voice-start', () => {
  log('[ipc] 收到 voice-start');
  startCall().catch((e) => log('[通话] 接通异常:', e.message));
});
ipcMain.on('voice-stop', () => {
  log('[ipc] 收到 voice-stop');
  stopCall().catch((e) => log('[通话] 挂断异常:', e.message));
});
ipcMain.handle('voice-say', (_e, text) => voicePost('/say', { text }));
ipcMain.on('menu', () => {
  log('[ipc] 收到 menu 请求');
  if (!win) return log('  没有窗口');
  try {
    const menu = buildMenu();
    menu.popup({ window: win, callback: () => log('  菜单已关闭') });
    log('  菜单已弹出，项数=', menu.items.length);
  } catch (e) {
    log('  菜单弹出失败：', e.message);
  }
});
ipcMain.on('log', (_e, m) => log('[page]', m));
ipcMain.handle('speak', (_e, text) => speak(text));
ipcMain.on('stop', () => win && win.webContents.send('stop'));
ipcMain.on('close-input', () => inputWin && inputWin.close());

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => { if (win) { win.show(); win.focus(); } });
  app.whenReady().then(async () => {
    await ensureServer();
    createBall();
    log('悬浮球已启动：', pageUrl());
    ensureVoiceBridge().then((ok) => log('语音桥状态：', ok ? '可用' : '不可用'));
    if (process.env.BALL_SHOT) {
      setTimeout(async () => {
        try {
          const img = await win.webContents.capturePage();
          fs.writeFileSync(path.join(ROOT, 'logs', 'ball.png'), img.toPNG());
          log('已截图 logs/ball.png（', img.getSize().width, 'x', img.getSize().height, '）');
        } catch (e) { log('截图失败：', e.message); }
        app.quit();
      }, 6000);
    }
  });
  app.on('window-all-closed', () => app.quit());
}
