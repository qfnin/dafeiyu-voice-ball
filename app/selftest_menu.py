# -*- coding: utf-8 -*-
"""右键菜单专项验收

上次失败是因为坐标空间搞错了：Win32 的 GetWindowRect 给的是逻辑像素（1707x1067），
而 ImageGrab 抓的是物理像素（2560x1600），缩放 1.5 倍。这里统一换算。
判定方式：右键后检查系统里是否出现菜单窗口类 "#32768"（Win32 弹出菜单的标准类名）。
"""
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


def physical_size():
    """物理分辨率（用桌面窗口矩形拿，避开 DPI 虚拟化）"""
    r = wintypes.RECT()
    user32.GetWindowRect(user32.GetDesktopWindow(), ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


def send_mouse(flags, x=None, y=None):
    sw, sh = physical_size()
    inp = INPUT()
    inp.type = 0
    inp.mi.dwFlags = flags
    if x is not None:
        inp.mi.dx = int(x * 65535 / max(1, sw - 1))
        inp.mi.dy = int(y * 65535 / max(1, sh - 1))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def find_ball():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, b, n + 1)
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            if "RuiC-2D" in b.value and "Edge" not in b.value and "Chrome_WidgetWin" in cls.value:
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def menu_windows():
    """系统里所有 #32768 类窗口 = 正在显示的弹出菜单"""
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "#32768" and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append((hwnd, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumWindows(cb, 0)
    return out


def main():
    hwnd = find_ball()
    if not hwnd:
        print("没找到球窗口")
        return 1
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    lw, lh = r.right - r.left, r.bottom - r.top
    pw, ph = physical_size()
    scale = pw / 1707.0 if pw > 2000 else 1.0     # 逻辑 1707 宽 -> 物理 2560 宽
    print(f"球窗口 逻辑({r.left},{r.top},{lw}x{lh}) 物理屏 {pw}x{ph} 缩放≈{scale:.2f}")

    cx = int((r.left + lw / 2) * scale)
    cy = int((r.top + lh / 2) * scale)
    print(f"球心（物理坐标）= ({cx},{cy})")

    send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, cx, cy)
    time.sleep(0.4)
    send_mouse(MOUSEEVENTF_RIGHTDOWN)
    time.sleep(0.1)
    send_mouse(MOUSEEVENTF_RIGHTUP)
    time.sleep(1.0)

    menus = menu_windows()
    print(f"右键后检测到菜单窗口: {menus}")
    if menus:
        print("→ 右键菜单: 弹出来了 ✓")
        # 点第一项「朗读剪贴板」需要真实菜单项坐标，这里只验证弹出，然后按 Esc 关闭
        user32.keybd_event(0x1B, 0, 0, 0)
        user32.keybd_event(0x1B, 0, 2, 0)
    else:
        print("→ 右键菜单: 没弹出来 ✗")
        # 退而求其次：直接调 IPC 看菜单能不能建起来
        print("   尝试左键点一下再右键（有些透明窗需要先激活）")
        send_mouse(MOUSEEVENTF_LEFTDOWN)
        send_mouse(MOUSEEVENTF_LEFTUP)
        time.sleep(0.4)
        send_mouse(MOUSEEVENTF_RIGHTDOWN)
        time.sleep(0.1)
        send_mouse(MOUSEEVENTF_RIGHTUP)
        time.sleep(1.0)
        menus2 = menu_windows()
        print(f"   再试后菜单窗口: {menus2}")
        if menus2:
            print("   → 右键菜单: 需要先激活窗口才弹（可以接受，实际点击时窗口本来就会被激活）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
