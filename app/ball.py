"""RuiC-2D 桌面悬浮球（Edge app 窗口 + 本地桥）

渲染用**系统自带的 Edge**（不再起 Chromium 外壳）：从当前环境里新起的 Chromium 外壳，
GPU 进程会崩（WebGL 上下文丢失，页面全白）；而 Edge 复用用户已经在跑的浏览器进程，
渲染完全正常。
外壳只做三件事：
  1) ctypes 把 Edge 的 app 窗口去掉标题栏、裁成正圆、置顶、不进任务栏；
  2) 鼠标拖动 + tkinter 右键菜单；
  3) 一个本地小 HTTP 桥（默认 8797，带 CORS），页面每秒来取指令——说话、停止、重载。
所有缓存/配置/日志/音频都在项目目录（D 盘），注册表里只写一个开机自启项。
"""
import asyncio
import base64
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
LOG_PATH = ROOT / "logs" / "ball.log"
TTS_DIR = ROOT / "tts"
SITE = "http://127.0.0.1:8796"
RUIC_DIR = Path(os.environ.get("RUIC_HOME") or (ROOT.parent / "RuiC-2D"))
VENV_PY = RUIC_DIR / ".venv" / "Scripts" / "python.exe"
BRIDGE_PORT = 8797
CDP_PORT = 9333          # Edge 的远程调试端口（仅本机可访问，用来做渲染自检/切静态模式）
STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_NAME = "RuiC2DBall"
WINDOW_HINTS = ("pet.html", "RuiC-2D 悬浮球")
WINDOW_EXCLUDE = ("Microsoft\u200b Edge", "Microsoft Edge")

DEFAULTS = {
    "project": "da-fei-yu-1",
    "diameter": 340,
    "x": None,
    "y": None,
    "voice": "zh-CN-XiaoxiaoNeural",
    "rate": "+10%",
    "pitch": "+8Hz",
    "zoom": 1.52,
    "anchorY": 0.46,
    "max_chars": 300,
    "topmost": True,
}
for d in (ROOT / "logs", TTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# 这个变量（以及 DSH_* 注入变量）会让从本会话启动的 Chromium 子进程渲染崩掉，先清掉
os.environ.pop("ELECTRON_RUN_AS_NODE", None)
os.environ.setdefault("TMP", str(ROOT / "cache" / "tmp"))
os.environ.setdefault("TEMP", str(ROOT / "cache" / "tmp"))
(ROOT / "cache" / "tmp").mkdir(parents=True, exist_ok=True)

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CAPTION, WS_THICKFRAME, WS_SYSMENU = 0x00C00000, 0x00040000, 0x00080000
WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00020000, 0x00010000
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_TOPMOST = 0x00000080, 0x00040000, 0x00000008
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_FRAMECHANGED, SWP_SHOWWINDOW = 0x0001, 0x0002, 0x0010, 0x0020, 0x0040
SWP_NOSENDCHANGING = 0x0400        # 关键：别让 Chromium 收到 WM_WINDOWPOSCHANGING，否则它会把置顶改回去
WM_CLOSE = 0x0010
VK_LBUTTON, VK_RBUTTON = 0x01, 0x02

MESSAGES = queue.Queue()          # 给页面的指令
_last_poll = {"t": 0.0}
_LAST_FAIL_LOG = 0.0


def log(*parts):
    line = time.strftime("%H:%M:%S") + "  " + " ".join(str(p) for p in parts)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def load_config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig")))
    except FileNotFoundError:
        pass
    except Exception as exc:
        log("配置读取失败，用默认值：", exc)
    return cfg


def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        log("配置保存失败：", exc)


# ---------------------------------------------------------------- 桥（给页面取指令）
class Bridge(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/next"):
            _last_poll["t"] = time.time()
            try:
                msg = MESSAGES.get_nowait()
            except queue.Empty:
                msg = {"type": "idle"}
            body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        elif self.path.startswith("/ping"):
            body = b'{"ok":true}'
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def start_bridge():
    server = ThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), Bridge)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log("本地桥已监听 127.0.0.1:", BRIDGE_PORT)


# ---------------------------------------------------------------- Win32
def find_ball_window():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if any(h in buf.value for h in WINDOW_HINTS) and not any(x in buf.value for x in WINDOW_EXCLUDE):
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            if cls.value.startswith("Chrome_WidgetWin"):
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found


def window_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def shape_window(hwnd, diameter=None, topmost=True):
    """只把标题栏和方角用窗口区域裁掉。

    刻意不动 GWL_STYLE / GWL_EXSTYLE：实测一旦去掉 WS_CAPTION，Chromium 的合成就会失效
    （窗口还在、系统也说 visible，但屏幕上是空白/白盘）。用区域把非客户区一起裁掉，
    照样看不见标题栏，而且渲染保持正常。
    """
    x, y, w, h = window_rect(hwnd)
    cr = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(cr))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    offx, offy = pt.x - x, pt.y - y
    side = min(cr.right, cr.bottom)
    if diameter:
        scale = 1.0
        try:
            scale = user32.GetDpiForWindow(hwnd) / 96.0 or 1.0
        except Exception:
            pass
        side = min(side, int(round(diameter * scale)))
    rgn = gdi32.CreateEllipticRgn(offx, offy, offx + side + 1, offy + side + 1)
    if rgn:
        user32.SetWindowRgn(hwnd, rgn, True)
    ctypes.set_last_error(0)
    ok = user32.SetWindowPos(hwnd, HWND_TOPMOST if topmost else HWND_NOTOPMOST, x, y, w, h,
                             SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOSENDCHANGING)
    if not ok:
        err = ctypes.get_last_error()
        global _LAST_FAIL_LOG
        if time.time() - _LAST_FAIL_LOG > 60:
            _LAST_FAIL_LOG = time.time()
            log(f"置顶/裁圆失败 err={err}；这台机器上 Edge 以管理员权限运行，"
                f"普通权限的助手改不动它的窗口——改用 Electron 外壳，或右键「以管理员身份运行」启动器")
    return bool(ok)


def cursor_pos():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def clipboard_text():
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(13)
        if not handle:
            return ""
        ptr = ctypes.windll.kernel32.GlobalLock(handle)
        try:
            return ctypes.c_wchar_p(ptr).value or ""
        finally:
            ctypes.windll.kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


# ---------------------------------------------------------------- 语音
async def _synth(text, voice, rate, pitch, out):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(out))


def speak(text, cfg):
    text = (text or "").strip()[: int(cfg["max_chars"])]
    if not text:
        return
    out = TTS_DIR / "last.mp3"
    try:
        asyncio.run(_synth(text, cfg["voice"], cfg["rate"], cfg["pitch"], out))
    except Exception as exc:
        log("合成失败：", exc)
        return
    data = out.read_bytes()
    url = "data:audio/mpeg;base64," + base64.b64encode(data).decode("ascii")
    MESSAGES.put({"type": "speak", "url": url})
    log(f"合成 {len(text)} 字 -> {len(data)} 字节，已排队")


# ---------------------------------------------------------------- 服务 / Edge
def ensure_server():
    import socket
    for _ in range(2):
        with socket.socket() as s:
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", 8796)) == 0:
                return True
        env = dict(os.environ)
        if VENV_PY.exists():
            env["YOUXING_PYTHON"] = str(VENV_PY)
        try:
            subprocess.Popen(["node", "server.mjs"], cwd=str(RUIC_DIR), env=env,
                             creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log("已拉起 RuiC-2D 服务")
        except Exception as exc:
            log("拉起服务失败：", exc)
        time.sleep(2.5)
    return False


def find_edge_exe():
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(p).exists():
            return p
    return "msedge.exe"


def page_url(cfg, static=False):
    url = (f"{SITE}/pet.html?project={cfg['project']}&zoom={cfg['zoom']}"
           f"&anchorY={cfg['anchorY']}&size=100%&bridge={BRIDGE_PORT}")
    return url + ("&static=1" if static else "")


# ---------------------------------------------------------------- 渲染自检（CDP）
def _cdp_page(timeout=6.0):
    """拿到 pet 页面的 websocket 地址"""
    import urllib.request
    for _ in range(40):
        try:
            targets = json.loads(urllib.request.urlopen(
                f"http://127.0.0.1:{CDP_PORT}/json", timeout=3).read())
            for t in targets:
                if t.get("type") == "page" and "pet.html" in (t.get("url") or ""):
                    return t.get("webSocketDebuggerUrl")
            return None
        except Exception:
            time.sleep(0.5)
    return None


def cdp_call(method, params=None, timeout=8.0):
    """调一次 CDP（自己开一条临时连接，够用且简单）"""
    try:
        import websocket
    except ImportError:
        log("缺少 websocket-client，跳过 CDP 调用")
        return None
    ws_url = _cdp_page()
    if not ws_url:
        return None
    try:
        ws = websocket.create_connection(ws_url, timeout=timeout)
        ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                ws.close()
                return msg
    except Exception as exc:
        log("CDP 调用失败：", method, exc)
        return None


def look_blank_ratio(cfg):
    """给页面截图并算「空白像素占比」：透明或接近纯白都算空白"""
    msg = cdp_call("Page.enable")
    if msg is None:
        return None
    msg = cdp_call("Page.captureScreenshot", {"format": "png"}, timeout=12)
    data = ((msg or {}).get("result") or {}).get("data")
    if not data:
        return None
    try:
        import io
        from PIL import Image
    except ImportError:
        return None
    img = Image.open(io.BytesIO(base64.b64decode(data))).convert("RGBA").resize((64, 64))
    blank = 0
    for r, g, b, a in img.getdata():
        if a < 20 or (r > 232 and g > 232 and b > 232):
            blank += 1
    return blank / (64 * 64)


def launch_edge(cfg):
    """用独立的 Edge 配置目录启动 app 窗口：不打扰用户正在跑的 Edge（它可能是管理员权限，
    直接复用会弹「是否用普通权限重启」的对话框），也不会被它的策略影响。"""
    edge_profile = ROOT / "cache" / "edge-profile"
    edge_profile.mkdir(parents=True, exist_ok=True)
    args = [find_edge_exe(), f"--app={page_url(cfg)}",
            f"--user-data-dir={edge_profile}",
            "--remote-debugging-port=" + str(CDP_PORT),   # 仅本机可访问，用来诊断/自检
            f"--window-size={cfg['diameter']},{cfg['diameter']}",
            "--window-position=" + (f"{cfg['x']},{cfg['y']}" if cfg.get("x") is not None else "300,200"),
            "--no-first-run", "--no-default-browser-check",
            "--autoplay-policy=no-user-gesture-required"]
    log("打开 Edge app 窗口（独立配置目录）")
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        log("启动 Edge 失败：", exc)


# ---------------------------------------------------------------- 开机自启
def startup_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY) as key:
            winreg.QueryValueEx(key, STARTUP_NAME)
        return True
    except OSError:
        return False


def set_startup(enabled):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY) as key:
        if enabled:
            pyw = Path(sys.executable).with_name("pythonw.exe")
            winreg.SetValueEx(key, STARTUP_NAME, 0, winreg.REG_SZ,
                              f'"{pyw}" "{Path(__file__).resolve()}"')
        else:
            try:
                winreg.DeleteValue(key, STARTUP_NAME)
            except OSError:
                pass
    return startup_enabled()


# ---------------------------------------------------------------- 主流程
def main():
    cfg = load_config()
    ensure_server()
    start_bridge()

    stop = threading.Event()
    actions = queue.Queue()
    state = {"hwnd": None, "topmost": cfg.get("topmost", True)}

    windows = find_ball_window()
    if not windows:
        launch_edge(cfg)
        for _ in range(180):          # 首次开新配置目录时 Edge 起得慢，最多等 90 秒
            windows = find_ball_window()
            if windows:
                break
            time.sleep(0.5)
    if windows:
        state["hwnd"] = windows[0]
        shape_window(state["hwnd"], cfg["diameter"], state["topmost"])
        log("窗口已裁圆 hwnd=", state["hwnd"], "rect=", window_rect(state["hwnd"]))
    else:
        log("暂时没找到 Edge 窗口，继续等（看门狗会接手）")

    def mouse_loop():
        dragging = False
        grab = (0, 0)
        while not stop.is_set():
            time.sleep(0.02)
            h = state["hwnd"]
            if not h or not user32.IsWindow(h):
                continue
            x, y, w, hh = window_rect(h)
            cx, cy = cursor_pos()
            inside = x <= cx <= x + w and y <= cy <= y + hh
            if key_down(VK_LBUTTON):
                if not dragging and inside:
                    dragging, grab = True, (cx - x, cy - y)
                elif dragging:
                    user32.SetWindowPos(h, HWND_TOPMOST if state["topmost"] else HWND_NOTOPMOST,
                                        cx - grab[0], cy - grab[1], 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
            elif dragging:
                dragging = False
                nx, ny, _, _ = window_rect(h)
                cfg["x"], cfg["y"] = nx, ny
                save_config(cfg)
            if key_down(VK_RBUTTON) and inside:
                while key_down(VK_RBUTTON):
                    time.sleep(0.02)
                actions.put("menu")
                time.sleep(0.35)

    threading.Thread(target=mouse_loop, daemon=True).start()

    def render_check():
        """页面起来后自检一次：如果基本空白（WebGL 在这台机器上偶尔会挂），
        就带着 static=1 重新导航，改走「静态立绘 + 呼吸/说话动作」，球里一定有角色。"""
        time.sleep(10)
        ratio = look_blank_ratio(cfg)
        if ratio is None:
            log("渲染自检：拿不到页面截图，跳过")
            return
        log(f"渲染自检：空白像素占比 {ratio:.1%}")
        if ratio > 0.9:
            static_url = page_url(cfg, static=True)
            log("页面基本空白，切静态模式：", static_url)
            cdp_call("Runtime.evaluate", {"expression": f"location.href={json.dumps(static_url)}"})

    threading.Thread(target=render_check, daemon=True).start()

    def has_region(h):
        hdc = user32.GetWindowDC(h)
        try:
            return gdi32.GetWindowRgn(h, hdc) > 1   # 2=简单区域 3=复杂区域；0/1 表示没有区域
        finally:
            user32.ReleaseDC(h, hdc)

    def watchdog():
        while not stop.is_set():
            time.sleep(1.5)
            h = state["hwnd"]
            if not h or not user32.IsWindow(h):
                found = find_ball_window()
                if found:
                    state["hwnd"] = found[0]
                    shape_window(found[0], cfg["diameter"], state["topmost"])
                continue
            if not has_region(h):
                shape_window(h, cfg["diameter"], state["topmost"])
            else:
                user32.SetWindowPos(h, HWND_TOPMOST if state["topmost"] else HWND_NOTOPMOST,
                                    0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    threading.Thread(target=watchdog, daemon=True).start()

    # ---- tkinter：右键菜单 + 输入框（主线程）
    root = tk.Tk()
    root.withdraw()

    def do_speak():
        text = clipboard_text()
        if not text.strip():
            log("剪贴板没有文字")
            return
        threading.Thread(target=speak, args=(text, cfg), daemon=True).start()

    def do_input():
        dlg = tk.Toplevel(root)
        dlg.title("跟悬浮球说话")
        dlg.attributes("-topmost", True)
        dlg.geometry("440x150+%d+%d" % (cursor_pos()[0] - 220, cursor_pos()[1] + 20))
        tk.Label(dlg, text="让悬浮球说这句话（回车发送 · Esc 取消）").pack(pady=(12, 6))
        entry = tk.Entry(dlg, width=48)
        entry.pack(pady=4)
        entry.focus_set()

        def send(_=None):
            text = entry.get()
            dlg.destroy()
            if text.strip():
                threading.Thread(target=speak, args=(text, cfg), daemon=True).start()

        tk.Button(dlg, text="说", width=10, command=send).pack(pady=6)
        dlg.bind("<Return>", send)
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    def toggle_top():
        state["topmost"] = not state["topmost"]
        cfg["topmost"] = state["topmost"]
        save_config(cfg)
        h = state["hwnd"]
        if h:
            user32.SetWindowPos(h, HWND_TOPMOST if state["topmost"] else HWND_NOTOPMOST,
                                0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def reload_page():
        MESSAGES.put({"type": "reload"})

    def quit_all():
        h = state["hwnd"]
        if h and user32.IsWindow(h):
            user32.PostMessageW(h, WM_CLOSE, 0, 0)
        stop.set()
        root.quit()

    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="朗读剪贴板", command=do_speak)
    menu.add_command(label="输入文字说话…", command=do_input)
    menu.add_command(label="停止说话", command=lambda: MESSAGES.put({"type": "stop"}))
    menu.add_separator()
    menu.add_command(label="窗口置顶（切换）", command=toggle_top)
    menu.add_command(label="开机自启（切换）", command=lambda: log("开机自启 ->", set_startup(not startup_enabled())))
    menu.add_command(label="重新载入角色", command=reload_page)
    menu.add_separator()
    menu.add_command(label="退出悬浮球", command=quit_all)

    log("悬浮球就绪：", page_url(cfg))
    while not stop.is_set():
        try:
            while True:
                if actions.get_nowait() == "menu":
                    x, y = cursor_pos()
                    try:
                        menu.tk_popup(x, y)
                    finally:
                        menu.grab_release()
        except queue.Empty:
            pass
        try:
            root.update()
        except tk.TclError:
            break
        if time.time() - _last_poll["t"] > 20 and _last_poll["t"] > 0:
            log("页面已经 20 秒没来取指令了，可能被关掉了")
            _last_poll["t"] = time.time()
        time.sleep(0.03)
    log("已退出")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log("外壳崩溃：\n" + traceback.format_exc())
        raise
