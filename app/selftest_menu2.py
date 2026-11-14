# -*- coding: utf-8 -*-
"""右键菜单验收 v2：右键后立刻连拍，看球下方是否出现「浅色矩形菜单块」"""
import ctypes
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

user32 = ctypes.WinDLL("user32", use_last_error=True)
OUT = Path(__file__).resolve().parents[1] / "logs"

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


def ball_rect():
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
                out.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumWindows(cb, 0)
    return out[0] if out else None


def light_ratio(img):
    """浅色（接近白/浅灰）像素占比 —— 菜单块是浅色"""
    small = img.convert("RGB").resize((40, 40))
    px = list(small.getdata())
    light = sum(1 for r, g, b in px if r > 225 and g > 225 and b > 225) / len(px)
    return light


def main():
    rect = ball_rect()
    if not rect:
        print("没找到球")
        return 1
    x, y, w, h = rect
    cx, cy = x + w // 2, y + h // 2
    print(f"球 rect=({x},{y},{w}x{h}) 中心=({cx},{cy})")

    base = ImageGrab.grab(all_screens=True)
    box = (max(0, cx - 60), max(0, cy - 60), cx + 300, cy + 360)
    base_light = light_ratio(base.crop(box))
    print(f"右键前：球右下方浅色占比 {base_light:.1%}")

    send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, cx, cy)
    time.sleep(0.5)
    send(MOUSEEVENTF_RIGHTDOWN)
    time.sleep(0.12)
    send(MOUSEEVENTF_RIGHTUP)

    peak = base_light
    for i in range(8):
        time.sleep(0.18)
        img = ImageGrab.grab(all_screens=True)
        lr = light_ratio(img.crop(box))
        peak = max(peak, lr)
        if i in (0, 3, 7):
            img.crop(box).save(OUT / f"menu-v2-{i}.png")
        print(f"  +{(i+1)*0.18:.2f}s 浅色占比 {lr:.1%}")

    print(f"\n浅色峰值 {peak:.1%}（基线 {base_light:.1%}）")
    if peak > base_light + 0.15:
        print("→ 右键菜单: 弹出来了 ✓")
    else:
        print("→ 右键菜单: 屏幕上没看到菜单块 ✗")

    # 关掉菜单
    send(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.05)
    send(MOUSEEVENTF_LEFTUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
