# -*- coding: utf-8 -*-
"""右键菜单验收 v4：右键后枚举「新出现的窗口」，这是最直接的证据"""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

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


def visible_windows():
    out = {}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if not user32.IsWindowVisible(h):
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, cls, 256)
        n = user32.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, b, n + 1)
        r = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        out[h] = (cls.value, b.value[:40], r.left, r.top, r.right - r.left, r.bottom - r.top)
        return True

    user32.EnumWindows(cb, 0)
    return out


def ball_rect():
    for h, (cls, title, x, y, w, hh) in visible_windows().items():
        if "RuiC-2D" in title and "Edge" not in title and "Chrome_WidgetWin" in cls:
            return x, y, w, hh
    return None


def main():
    rect = ball_rect()
    if not rect:
        print("没找到球")
        return 1
    x, y, w, h = rect
    cx, cy = x + w // 2, y + h // 2

    before = visible_windows()
    print(f"右键前可见窗口数: {len(before)}")

    send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, cx, cy)
    time.sleep(0.4)
    send(MOUSEEVENTF_RIGHTDOWN)
    time.sleep(0.12)
    send(MOUSEEVENTF_RIGHTUP)
    time.sleep(0.8)

    after = visible_windows()
    new = {h: v for h, v in after.items() if h not in before}
    print(f"右键后可见窗口数: {len(after)}，新增 {len(new)} 个：")
    for h, (cls, title, wx, wy, ww, wh) in new.items():
        print(f"  hwnd={h} class={cls!r} title={title!r} rect=({wx},{wy},{ww}x{wh})")
        if "menu" in cls.lower() or cls == "#32768" or (ww > 100 and wh > 80):
            print("    ↑ 这看起来就是弹出的菜单")

    if new:
        print("→ 右键菜单: 弹出来了 ✓")
    else:
        print("→ 右键菜单: 没有新窗口出现 ✗")

    send(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.05)
    send(MOUSEEVENTF_LEFTUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
