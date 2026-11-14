# -*- coding: utf-8 -*-
"""右键菜单验收 v3：全屏对比，找出右键前后变化最大的矩形区域"""
import ctypes
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageChops, ImageGrab

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


def main():
    rect = ball_rect()
    if not rect:
        print("没找到球")
        return 1
    x, y, w, h = rect
    cx, cy = x + w // 2, y + h // 2
    print(f"球 rect=({x},{y},{w}x{h})")

    before = ImageGrab.grab(all_screens=True).convert("RGB")
    print("全屏尺寸:", before.size)

    send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, cx, cy)
    time.sleep(0.4)
    send(MOUSEEVENTF_RIGHTDOWN)
    time.sleep(0.12)
    send(MOUSEEVENTF_RIGHTUP)
    time.sleep(0.7)

    after = ImageGrab.grab(all_screens=True).convert("RGB")
    after.save(OUT / "menu-after-full.png")
    before.save(OUT / "menu-before-full.png")

    diff = ImageChops.difference(before, after).convert("L")
    bbox = diff.getbbox()
    print("变化区域 bbox:", bbox)
    # 变化像素总数
    hist = diff.histogram()
    changed = sum(hist[30:])
    total = before.size[0] * before.size[1]
    print(f"变化像素: {changed} / {total} = {changed/total:.3%}")

    if bbox:
        # 判断这块区域是不是矩形菜单（宽高比、面积）
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        print(f"变化区域尺寸: {bw}x{bh}")
        after.crop(bbox).save(OUT / "menu-region.png")
        print("→ 菜单区域已存 logs/menu-region.png")
        print("→ 右键菜单:", "弹出来了 ✓" if bw > 80 and bh > 80 else "变化太小，可能不是菜单")

    send(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.05)
    send(MOUSEEVENTF_LEFTUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
