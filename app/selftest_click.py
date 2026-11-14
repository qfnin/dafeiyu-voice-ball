# -*- coding: utf-8 -*-
"""用真实鼠标点球上的电话按钮，看后端有没有收到

按钮在页面里是 (180, 311)，球窗口在屏幕上是 (x, y, 360, 360)，
所以按钮的屏幕坐标 = 窗口左上角 + 页面坐标（窗口无边框，1:1）。
"""
import ctypes
import json
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
user32 = ctypes.WinDLL("user32", use_last_error=True)

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
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


def ball_window():
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        n = user32.GetWindowTextLengthW(h)
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, b, n + 1)
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, cls, 256)
            if "RuiC-2D" in b.value and "Edge" not in b.value and "Chrome_WidgetWin" in cls.value:
                r = wintypes.RECT()
                user32.GetWindowRect(h, ctypes.byref(r))
                out.append((h, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumWindows(cb, 0)
    return out[0] if out else None


def log_tail(path, n=6):
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except Exception:
        return []


def main():
    w = ball_window()
    if not w:
        print("没找到球窗口")
        return 1
    hwnd, wx, wy, ww, wh = w
    print(f"球窗口 hwnd={hwnd} 屏幕位置 ({wx},{wy}) 尺寸 {ww}x{wh}")

    # 页面里的按钮坐标（上一轮诊断结果）
    bx, by = 180, 311
    sx, sy = wx + bx, wy + by
    print(f"按钮屏幕坐标 = ({sx},{sy})")

    before = len(log_tail(ROOT / "logs" / "shell.log", 200))
    print("\n把鼠标移过去并点击…")
    send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, sx, sy)
    time.sleep(0.6)
    # 先看看鼠标下面是哪个窗口
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    u2 = ctypes.WinDLL("user32")
    u2.WindowFromPoint.restype = wintypes.HWND
    under = u2.WindowFromPoint(POINT(sx, sy))
    print(f"该坐标下的窗口: {under}  (球窗口是 {hwnd})")
    print("  同窗口吗:", "是" if under == hwnd else "不是！鼠标被别的窗口挡住了")

    send(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.12)
    send(MOUSEEVENTF_LEFTUP)
    print("已点击，等 3 秒看后端反应…")
    time.sleep(3)

    print("\n=== shell.log 新增 ===")
    for line in log_tail(ROOT / "logs" / "shell.log", 8):
        print("  " + line)
    print("\n=== voice.log 新增 ===")
    for line in log_tail(ROOT / "logs" / "voice.log", 6):
        print("  " + line)

    try:
        with urllib.request.urlopen("http://127.0.0.1:8798/status", timeout=5) as r:
            print("\n桥状态:", r.read().decode())
    except Exception as e:
        print("桥状态读取失败:", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
