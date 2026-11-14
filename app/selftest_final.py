# -*- coding: utf-8 -*-
"""最终验收：菜单 -> 输入框 -> 打字 -> 回车 -> 球说话

输入框是 Electron 窗口（title="跟悬浮球说话"），用标题精确找它。
"""
import ctypes
import json
import time
import urllib.request
from ctypes import wintypes

import websocket

user32 = ctypes.WinDLL("user32", use_last_error=True)
KEYEVENTF_KEYUP = 0x0002
VK_RETURN = 0x0D

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


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


def find_window(title_part):
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, b, n + 1)
                if title_part in b.value:
                    r = wintypes.RECT()
                    user32.GetWindowRect(h, ctypes.byref(r))
                    out.append((h, b.value, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumWindows(cb, 0)
    return out


def ball():
    for h, title, x, y, w, hh in find_window("RuiC-2D"):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, cls, 256)
        if "Chrome_WidgetWin" in cls.value and "Edge" not in title:
            return x, y, w, hh
    return None


def type_unicode(text):
    """直接给焦点窗口发 WM_CHAR，中文也能进"""
    hwnd = user32.GetForegroundWindow()
    for ch in text:
        user32.SendMessageW(hwnd, 0x0102, ord(ch), 0)
        time.sleep(0.02)


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
    print(f"[0] 球 rect=({x},{y},{w}x{h})")

    # 关掉可能残留的输入框
    for hw, title, *_ in find_window("跟悬浮球说话"):
        user32.PostMessageW(hw, 0x0010, 0, 0)
    time.sleep(0.5)

    print("[1] 右键球心打开菜单")
    send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, cx, cy)
    time.sleep(0.3)
    send(MOUSEEVENTF_RIGHTDOWN)
    time.sleep(0.12)
    send(MOUSEEVENTF_RIGHTUP)
    time.sleep(0.8)

    menus = [w for w in find_window("") if w[0] and not w[1]]
    cls_menu = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def scan(hw, _):
        if user32.IsWindowVisible(hw):
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hw, cls, 256)
            n = user32.GetWindowTextLengthW(hw)
            if "Chrome_WidgetWin" in cls.value and n == 0:
                rr = wintypes.RECT()
                user32.GetWindowRect(hw, ctypes.byref(rr))
                if rr.right - rr.left > 80 and rr.bottom - rr.top > 80:
                    cls_menu.append((hw, rr.left, rr.top, rr.right - rr.left, rr.bottom - rr.top))
        return True
    user32.EnumWindows(scan, 0)
    print(f"    菜单窗口: {cls_menu}")
    if not cls_menu:
        print("    菜单没弹出")
        return 1
    mx, my, mw, mh = cls_menu[0][1], cls_menu[0][2], cls_menu[0][3], cls_menu[0][4]

    print("[2] 点「输入文字说话…」")
    item_h = (mh - 18) / 7.0
    tx, ty = mx + mw // 2, int(my + item_h + 9 + item_h / 2)
    send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, tx, ty)
    time.sleep(0.2)
    send(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.06)
    send(MOUSEEVENTF_LEFTUP)
    time.sleep(1.8)

    dlg = find_window("跟悬浮球说话")
    print(f"[3] 输入框: {[(d[1], d[2], d[3], d[4], d[5]) for d in dlg]}")
    if not dlg:
        print("    输入框没出现")
        return 1
    dh, dtitle, dx, dy, dw, dhh = dlg[0]

    print("[4] 点击输入区并打字")
    user32.SetForegroundWindow(dh)
    time.sleep(0.3)
    send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx + dw // 2, dy + int(dhh * 0.45))
    time.sleep(0.2)
    send(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.05)
    send(MOUSEEVENTF_LEFTUP)
    time.sleep(0.4)
    text = "你好，我是大肥鱼1号，现在会说话啦。"
    type_unicode(text)
    time.sleep(0.4)
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
    print(f"    已输入: {text}")

    print("[5] 观察球是否说话")
    for i in range(7):
        time.sleep(0.9)
        d = cdp("JSON.stringify(window.pet.debug())")
        print(f"    +{(i+1)*0.9:.1f}s {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
