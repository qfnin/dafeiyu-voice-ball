// 预加载：把外壳能力暴露给页面（pet.js 里按 window.ballShell 使用）
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ballShell', {
  kind: 'electron',
  onSpeak: (cb) => ipcRenderer.on('speak', (_e, url) => cb(url)),
  onStop: (cb) => ipcRenderer.on('stop', () => cb()),
  onVoiceState: (cb) => ipcRenderer.on('voice-state', (_e, d) => cb(d)),
  speak: (text) => ipcRenderer.invoke('speak', text),
  voiceStart: () => ipcRenderer.send('voice-start'),
  voiceStop: () => ipcRenderer.send('voice-stop'),
  voiceSay: (text) => ipcRenderer.invoke('voice-say', text),
  log: (msg) => ipcRenderer.send('log', msg),
  menu: () => sendMenu(),
});

// 拖动 + 右键。
// 坑：一次右键会同时触发 mousedown(button=2)、contextmenu、以及 document 冒泡，
// 如果每个都发一次 menu，后一次 popup 会把前一次顶掉 → 菜单一闪就没。所以这里统一去抖。
let dragActive = false;
let lastMenuAt = 0;

function sendMenu() {
  const now = Date.now();
  if (now - lastMenuAt < 350) return;   // 350ms 内的重复请求直接忽略
  lastMenuAt = now;
  ipcRenderer.send('menu');
}

addEventListener('mousedown', (e) => {
  if (e.button === 0) {
    // 点在通话按钮上时不要开始拖动，否则按钮点不动
    const t = e.target;
    if (t && t.closest && t.closest('#call')) return;
    dragActive = true;
    document.body && document.body.classList.add('dragging');
    ipcRenderer.send('drag-start');
  } else if (e.button === 2) {
    sendMenu();
  }
}, true);

addEventListener('mouseup', (e) => {
  if (e.button === 0 && dragActive) {
    dragActive = false;
    document.body && document.body.classList.remove('dragging');
    ipcRenderer.send('drag-end');
  }
}, true);

addEventListener('blur', () => {
  if (dragActive) {
    dragActive = false;
    document.body && document.body.classList.remove('dragging');
    ipcRenderer.send('drag-end');
  }
});

// 只负责阻止默认菜单，不再重复发请求
addEventListener('contextmenu', (e) => {
  e.preventDefault();
  e.stopPropagation();
}, true);
