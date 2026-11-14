// 渲染自检（可换 URL）：判断 Electron 在公司这台机器上能画什么、不能画什么
const { app, BrowserWindow } = require('electron');
const fs = require('fs');

app.commandLine.appendSwitch('force-device-scale-factor', '1');

const TARGET = process.env.MINI_URL || 'data:text/html,<body style="margin:0;background:#123"></body>';
const SIZE = Number(process.env.MINI_SIZE || 400);
const OUT = process.env.MINI_OUT || 'mini.png';
const TRANSPARENT = process.env.MINI_TRANSPARENT === '1';
const REGION = process.env.MINI_REGION === '1';
const OPTS = process.env.MINI_OPTS || '';
const path = require('path');

app.whenReady().then(async () => {
  const extra = {};
  if (OPTS.includes('ato')) {
    Object.assign(extra, { alwaysOnTop: true, skipTaskbar: true, hasShadow: false, resizable: false });
  }
  if (OPTS.includes('preload')) {
    extra.webPreferences = { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false };
  }
  if (OPTS.includes('userdata')) {
    app.setPath('userData', path.join(__dirname, '..', 'cache', 'electron-userdata'));
  }
  const win = new BrowserWindow(Object.assign({
    width: SIZE, height: SIZE, frame: false, show: true,
    transparent: TRANSPARENT,
    backgroundColor: TRANSPARENT ? '#00000000' : '#12162a',
    webPreferences: { contextIsolation: true, nodeIntegration: false, backgroundThrottling: false },
  }, extra));
  try {
    await win.loadURL(TARGET);
  } catch (e) { console.log('loadURL failed', e.message); }
  if (OPTS.includes('ss')) {
    win.setAlwaysOnTop(true, 'screen-saver');
    console.log('applied setAlwaysOnTop(screen-saver)');
  }
  if (REGION) {
    setTimeout(() => {
      try {
        const { spawn } = require('child_process');
        const buf = Buffer.from(win.getNativeWindowHandle());
        const hwnd = buf.length >= 8 ? buf.readBigUInt64LE(0).toString() : String(buf.readUInt32LE(0));
        const script = 'import ctypes,sys\n' +
          'from ctypes import wintypes\n' +
          'u=ctypes.WinDLL("user32"); g=ctypes.WinDLL("gdi32")\n' +
          'u.SetWindowRgn.argtypes=[wintypes.HWND, wintypes.HRGN, wintypes.BOOL]\n' +
          'h=int(sys.argv[1]); w=int(sys.argv[2])\n' +
          'rgn=g.CreateEllipticRgn(0,0,w+1,w+1)\n' +
          'print("region ret", u.SetWindowRgn(h, rgn, True))\n';
        const ruic = process.env.RUIC_HOME || require('path').resolve(__dirname, '..', '..', 'RuiC-2D');
        const py = require('path').join(ruic, '.venv', 'Scripts', 'python.exe');
        const f = require('path').join(require('os').tmpdir(), 'mini_circle.py');
        require('fs').writeFileSync(f, script, 'utf8');
        const p = spawn(py, [f, hwnd, String(SIZE)], { windowsHide: true });
        p.stdout.on('data', (d) => console.log('circle:', d.toString().trim()));
      } catch (e) { console.log('region failed', e.message); }
    }, 1200);
  }
  setTimeout(async () => {
    try {
      const img = await win.webContents.capturePage();
      const png = img.toPNG();
      fs.writeFileSync(OUT, png);
      const size = img.getSize();
      console.log(JSON.stringify({ out: OUT, bytes: png.length, w: size.width, h: size.height }));
    } catch (e) { console.log('capture failed', e.message); }
    app.quit();
  }, 6000);
});
