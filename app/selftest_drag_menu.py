# -*- coding: utf-8 -*-
"""验收：拖动 + 右键菜单 + 说话

不依赖肉眼：
  - 拖动：记下球窗口位置 -> 在球心按下并移动 -> 再看窗口位置有没有跟着走
  - 右键菜单：在球心右键 -> 抓屏，看球附近有没有冒出「菜单色块」（浅色矩形）
  - 说话：通过 CDP 触发，看口型包络 / talking 状态
"""
import ctypes
import json
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

import websocket
from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
user32 = ctypes.WinDLL("user32", use_last_error=True)

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
SM_CXSCREEN, SM_CYSCREEN = 0, 1


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("mi", MOUSEINPUT)]


def send_mouse(flags, x=None, y=None):
    inp = INPUT()
    inp.type = 0
    inp.mi.dwFlags = flags
    if x is not None:
        sw, sh = user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN)
        inp.mi.dx = int(x * 65535 / (sw - 1))
        inp.mi.dy = int(y * 65535 / (sh - 1))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def move_to(x, y):
    send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, x, y)


def find_ball_window():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            if "RuiC-2D" in buf.value and "Edge" not in buf.value and "Chrome_WidgetWin" in cls.value:
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def cdp_eval(expr):
    try:
        targets = json.loads(urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=4).read())
    except Exception:
        return None
    url = next((t["webSocketDebuggerUrl"] for t in targets
                if t.get("type") == "page" and "pet.html" in (t.get("url") or "")), None)
    if not url:
        return None
    ws = websocket.create_connection(url, timeout=20)
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == 1:
            ws.close()
            return (msg.get("result") or {}).get("result", {}).get("value")


def main():
    hwnd = find_ball_window()
    if not hwnd:
        print("没找到球窗口")
        return 1
    x, y, w, h = rect(hwnd)
    cx, cy = x + w // 2, y + h // 2
    print(f"球窗口 hwnd={hwnd} rect=({x},{y},{w},{h}) 中心=({cx},{cy})")

    # ---------- 拖动 ----------
    print("\n[拖动测试]")
    move_to(cx, cy)
    time.sleep(0.3)
    send_mouse(MOUSEEVENTF_LEFTDOWN)
    for step in range(1, 11):
        move_to(cx - step * 12, cy + step * 6)
        time.sleep(0.04)
    send_mouse(MOUSEEVENTF_LEFTUP)
    time.sleep(0.8)
    x2, y2, w2, h2 = rect(hwnd)
    print(f"  拖动后 rect=({x2},{y2})  位移=({x2-x}, {y2-y})")
    print("  → 拖动:", "有效" if abs(x2 - x) > 40 or abs(y2 - y) > 40 else "没动（可能被拒绝）")

    # 拖回原处
    move_to(x2 + w2 // 2, y2 + h2 // 2)
    time.sleep(0.3)
    send_mouse(MOUSEEVENTF_LEFTDOWN)
    dx, dy = x - x2, y - y2
    for step in range(1, 11):
        move_to(x2 + w2 // 2 + int(dx * step / 10), y2 + h2 // 2 + int(dy * step / 10))
        time.sleep(0.04)
    send_mouse(MOUSEEVENTF_LEFTUP)
    time.sleep(0.6)
    x3, y3, _, _ = rect(hwnd)
    print(f"  拖回后 rect=({x3},{y3})")

    # ---------- 右键菜单 ----------
    print("\n[右键菜单测试]")
    before = ImageGrab.grab(all_screens=True).convert("RGB")
    move_to(x3 + w2 // 2, y3 + h2 // 2)
    time.sleep(0.3)
    send_mouse(MOUSEEVENTF_RIGHTDOWN)
    time.sleep(0.08)
    send_mouse(MOUSEEVENTF_RIGHTUP)
    time.sleep(1.2)
    after = ImageGrab.grab(all_screens=True).convert("RGB")
    bx, by = x3, y3
    box = (bx, by, min(after.width, bx + 420), min(after.height, by + 420))
    a = before.crop(box).resize((100, 100))
    b = after.crop(box).resize((100, 100))
    pa, pb = list(a.getdata()), list(b.getdata())
    changed = sum(1 for p, q in zip(pa, pb) if abs(p[0]-q[0]) + abs(p[1]-q[1]) + abs(p[2]-q[2]) > 30)
    print(f"  右键后球周围变化像素比例: {changed/len(pa):.1%}")
    print("  → 菜单:", "弹出来了" if changed / len(pa) > 0.08 else "没看到明显变化")
    after.save(ROOT / "logs" / "menu-shot.png")
    # 关掉菜单
    send_mouse(MOUSEEVENTF_LEFTDOWN)
    send_mouse(MOUSEEVENTF_LEFTUP)
    time.sleep(0.5)

    # ---------- 说话 ----------
    print("\n[说话测试]")
    v = cdp_eval('window.ballShell.speak("测试一下，一二三四五六七八。").then(u=>u?("ok "+u.length):"empty")')
    print("  speak:", v)
    for i in range(5):
        time.sleep(0.9)
        d = cdp_eval("JSON.stringify(window.pet.debug())")
        print(f"   +{(i+1)*0.9:.1f}s", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
