/**
 * 大肥鱼语音球 · DSH 宿主侧插件
 *
 * 职责只有一件事：DSH 启动时把 scripts/ball-manager.mjs 作为子进程拉起来。
 * 管理进程自己负责：首次自动配置环境（克隆 RuiC-2D、建 venv、装依赖）→
 * 启动语音桥（whisper/LLM/TTS）→ 启动悬浮球 Electron 窗口 → 守护重启。
 * DSH 卸载/停用插件时，dispose 杀掉管理进程，由它带走全部子进程。
 */
import { spawn } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

export const name = 'dafeiyu-voice-ball';
export const inject = [];

/**
 * @param {import('cordis').Context} ctx
 */
export function apply(ctx) {
  let child = null;
  let disposed = false;

  const logInfo = (msg) => {
    try { ctx.logger?.info?.(`[dafeiyu-voice-ball] ${msg}`); } catch { console.log(`[dafeiyu-voice-ball] ${msg}`); }
  };
  const logWarn = (msg) => {
    try { ctx.logger?.warn?.(`[dafeiyu-voice-ball] ${msg}`); } catch { console.warn(`[dafeiyu-voice-ball] ${msg}`); }
  };

  const start = () => {
    if (disposed || child) return;
    try {
      child = spawn(process.execPath, [join(PKG_ROOT, 'scripts', 'ball-manager.mjs')], {
        cwd: PKG_ROOT,
        windowsHide: true,
        stdio: 'ignore',
        env: { ...process.env, DSH_MANAGED: '1' },
      });
      logInfo(`管理进程已启动 pid=${child.pid}（首次运行会自动配置环境，需要几分钟）`);
      child.on('exit', (code, signal) => {
        child = null;
        if (!disposed) {
          logWarn(`管理进程退出 code=${code} signal=${signal ?? ''}——悬浮球将不可用，重启 DSH 可再次拉起`);
        }
      });
      child.on('error', (e) => {
        child = null;
        logWarn(`管理进程启动失败: ${e.message}`);
      });
    } catch (e) {
      logWarn(`无法拉起管理进程: ${e?.message ?? e}`);
    }
  };

  // 卸载/停用插件时杀掉管理进程（管理进程会带走语音桥和悬浮球窗口）
  ctx.effect(() => () => {
    disposed = true;
    try {
      if (child) {
        child.kill();
        child = null;
        logInfo('已停止管理进程');
      }
    } catch { /* 进程已退出 */ }
  }, 'dafeiyu-voice-ball: stop manager');

  start();
}
