// 输入小窗的预加载
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ballShell', {
  kind: 'electron-input',
  speak: (text) => ipcRenderer.invoke('speak', text),
  closeInput: () => ipcRenderer.send('close-input'),
});
