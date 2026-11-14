# -*- coding: utf-8 -*-
"""只测「输入框」这一段：用键盘在菜单里选「输入文字说话…」

菜单是原生菜单，可以用方向键操作：右键后按 ↓ 一次到第二项，再按回车。
"""
import ctypes
import json
import time
import urllib.request
from ctypes import wintypes

import websocket

user32 = ctypes.WinDLL("user32", use_last_error=True)
KEYEVENTF_KEYUP = 0x0002
VK_DOWN, VK_RETURN, VK_ESCAPE = 0x28, 0x0D, 0x1B

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


def key(vk):
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)


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


def main():
    r = ball()
    if not r:
        print("没找到球")
        return 1
    x, y, w, h = r
    cx, cy = x + w // 2, y + h // 2
    print(f"球 rect=({x},{y},{w}x{h}) 中心=({cx},{cy})")

    before = set(windows())
    send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, cx, cy)
    time.sleep(0.3)
    send(MOUSEEVENTF_RIGHTDOWN)
    time.sleep(0.12)
    send(MOUSEEVENTF_RIGHTUP)
    time.sleep(0.7)

    menu_new = [v for k, v in windows().items() if k not in before]
    print("菜单窗口:", menu_new)
    if not menu_new:
        print("菜单没弹")
        return 1

    print("点击第二项「输入文字说话…」（按真实坐标：7 项 + 2 分隔符）")
    mx, my, mw, mh = menu_new[0][2], menu_new[0][3], menu_new[0][4], menu_new[0][5]
    sep_h = 9
    item_h = (mh - 2 * sep_h) / 7.0
    # 第 2 项：项1 + 分隔符 + 半个项
    ty = int(my + item_h + sep_h + item_h / 2)
    tx = mx + mw // 2
    print(f"  菜单 rect=({mx},{my},{mw}x{mh}) item_h={item_h:.1f} 点击 ({tx},{ty})")
    send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, tx, ty)
    time.sleep(0.2)
    send(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.06)
    send(MOUSEEVENTF_LEFTUP)
    time.sleep(1.8)

    wins = windows()
    new = [(k, v) for k, v in wins.items() if k not in before and v[0] != "Chrome_WidgetWin_1"]
    print(f"新窗口: {[(v[0], v[1], v[4], v[5]) for _, v in new]}")
    if new:
        print("→ 输入框出现 ✓")
    else:
        print("→ 输入框没出现 ✗")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
