# -*- coding: utf-8 -*-
"""验收：从右键菜单里点「输入文字说话…」-> 输入框出现 -> 打字 -> 回车 -> 球开口说话

全程不靠肉眼：每一步都用窗口枚举 + CDP 的 pet.debug() 拿证据。
"""
import ctypes
import json
import time
import urllib.request
from ctypes import wintypes

import websocket

user32 = ctypes.WinDLL("user32", use_last_error=True)

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("mi", MOUSEINPUT)]


def screen_size():
    r = wintypes.RECT()
    user32.GetWindowRect(user32.GetDesktopWindow(), ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


def send(flags, x=None, y=None):
    sw, sh = screen_size()
    inp = INPUT()
    inp.type = 0
    inp.mi.dwFlags = flags
    if x is not None:
        inp.mi.dx = int(x * 65535 / max(1, sw - 1))
        inp.mi.dy = int(y * 65535 / max(1, sh - 1))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def click(x, y):
    send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, x, y)
    time.sleep(0.15)
    send(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.05)
    send(MOUSEEVENTF_LEFTUP)


def type_text(text):
    """用 SendInput 逐字打 Unicode（WM_CHAR 方式）"""
    for ch in text:
        vk = 0
        user32.VkKeyScanW.restype = ctypes.c_short
        code = user32.VkKeyScanW(ord(ch))
        if code == -1:
            # 中文等非 ASCII：用 SendMessage WM_CHAR 到焦点窗口
            hwnd = user32.GetForegroundWindow()
            user32.SendMessageW(hwnd, 0x0102, ord(ch), 0)  # WM_CHAR
        else:
            vk = code & 0xFF
            shift = (code >> 8) & 0xFF
            if shift & 1:
                user32.keybd_event(0x10, 0, 0, 0)
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            if shift & 1:
                user32.keybd_event(0x10, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.03)


def windows():
    out = {}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if user32.IsWindowVisible(h):
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, cls, 256)
            n = user32.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, b, n + 1)
            r = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            out[h] = (cls.value, b.value, r.left, r.top, r.right - r.left, r.bottom - r.top)
        return True

    user32.EnumWindows(cb, 0)
    return out


def ball():
    for h, (cls, title, x, y, w, hh) in windows().items():
        if "RuiC-2D" in title and "Edge" not in title and "Chrome_WidgetWin" in cls:
            return x, y, w, hh
    return None


def cdp(expr):
    targets = json.loads(urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=5).read())
    url = next((t["webSocketDebuggerUrl"] for t in targets
                if t.get("type") == "page" and "pet.html" in (t.get("url") or "")), None)
    if not url:
        return None
    ws = websocket.create_connection(url, timeout=20)
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == 1:
            ws.close()
            return (m.get("result") or {}).get("result", {}).get("value")


def main():
    r = ball()
    if not r:
        print("没找到球")
        return 1
    x, y, w, h = r
    cx, cy = x + w // 2, y + h // 2
    print(f"球 rect=({x},{y},{w}x{h})")

    before = set(windows())
    print("\n[1] 右键球心")
    send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, cx, cy)
    time.sleep(0.3)
    send(MOUSEEVENTF_RIGHTDOWN)
    time.sleep(0.12)
    send(MOUSEEVENTF_RIGHTUP)
    time.sleep(0.8)
    after_menu = windows()
    new = [v for k, v in after_menu.items() if k not in before]
    if not new:
        print("  菜单没弹出")
        return 1
    mcls, mtitle, mx, my, mw, mh = new[0]
    print(f"  菜单窗口 rect=({mx},{my},{mw}x{mh})")

    print("\n[2] 点第二项「输入文字说话…」")
    # 菜单项高度约 = mh/9，第二项中心
    item_h = mh / 9.0
    tx, ty = mx + mw // 2, int(my + item_h * 1.5)
    print(f"  点击坐标 ({tx},{ty})")
    click(tx, ty)
    time.sleep(1.2)

    wins2 = windows()
    dlg = [(k, v) for k, v in wins2.items() if k not in after_menu]
    print(f"  新窗口: {[(v[0], v[1], v[4], v[5]) for _, v in dlg]}")
    if not dlg:
        print("  输入框没出现 ✗")
        return 1
    dcls, dtitle, dx, dy, dw, dh = dlg[0][1]
    print(f"  输入框 rect=({dx},{dy},{dw}x{dh}) title={dtitle!r} → 出现 ✓")

    print("\n[3] 打字并回车")
    click(dx + dw // 2, dy + int(dh * 0.45))
    time.sleep(0.4)
    type_text("测试一下，我是会说话的悬浮球。")
    time.sleep(0.4)
    user32.keybd_event(0x0D, 0, 0, 0)
    user32.keybd_event(0x0D, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(1.0)

    print("\n[4] 看球有没有在说话")
    for i in range(6):
        d = cdp("JSON.stringify(window.pet.debug())")
        print(f"  +{i+1}s {d}")
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
