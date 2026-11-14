# -*- coding: utf-8 -*-
"""验收检查：球是不是正圆、里面有没有角色、会不会动。

做法：整屏抓图 -> 在球色密集处裁一块 -> 看四角是否「不是球的颜色」（=被裁成圆）
      -> 连抓多帧，看球内像素是否变化（=角色在动）
"""
import time
from pathlib import Path

from PIL import ImageGrab

OUT = Path(__file__).resolve().parents[1] / "logs"


def ball_color(r, g, b):
    navy = r < 75 and g < 85 and 35 <= b <= 135 and b > r + 8
    ring = 95 <= r <= 170 and 135 <= g <= 200 and b >= 205
    return navy or ring


def locate(img):
    w, h = img.size
    rgb = img.convert("RGB")
    small = rgb.resize((w // 4, h // 4))
    sw, sh = small.size
    px = small.load()
    cell = 8
    hits = []
    for cy in range(0, sh - cell, cell):
        for cx in range(0, sw - cell, cell):
            n = 0
            for y in range(cy, cy + cell):
                for x in range(cx, cx + cell):
                    if ball_color(*px[x, y]):
                        n += 1
            if n > cell * cell * 0.5:
                hits.append((cx * 4, cy * 4))
    if not hits:
        return None
    xs = [h[0] for h in hits]
    ys = [h[1] for h in hits]
    pad = 24
    box = (max(0, min(xs) - pad), max(0, min(ys) - pad),
           min(w, max(xs) + cell * 4 + pad), min(h, max(ys) + cell * 4 + pad))
    return box


def corner_stats(img, box):
    crop = img.convert("RGB").crop(box)
    w, h = crop.size
    px = crop.load()
    k = max(4, min(w, h) // 12)

    def frac_ball(x0, y0, x1, y1):
        n = tot = 0
        for y in range(y0, y1):
            for x in range(x0, x1):
                tot += 1
                if ball_color(*px[x, y]):
                    n += 1
        return n / max(1, tot)

    corners = {
        "左上": frac_ball(0, 0, k, k),
        "右上": frac_ball(w - k, 0, w, k),
        "左下": frac_ball(0, h - k, k, h),
        "右下": frac_ball(w - k, h - k, w, h),
    }
    center = frac_ball(w // 2 - k, h // 2 - k, w // 2 + k, h // 2 + k)
    return corners, center, crop


def main():
    shots = []
    for i in range(4):
        img = ImageGrab.grab(all_screens=True)
        shots.append(img)
        time.sleep(0.7)

    img = shots[0]
    box = locate(img)
    if not box:
        print("屏幕上没找到球")
        return 1
    print(f"球所在区域（物理像素）: {box}  约 {box[2]-box[0]}x{box[3]-box[1]}")

    corners, center, crop = corner_stats(img, box)
    crop.save(OUT / "ball-onscreen.png")
    print("四角球色占比:", {k: f"{v:.1%}" for k, v in corners.items()})
    print(f"中心球色占比: {center:.1%}")
    is_round = all(v < 0.12 for v in corners.values()) and center > 0.25
    print("→ 圆形判定:", "是正圆（四角是空的）" if is_round else "四角也有颜色（还是方形/或没裁圆）")

    # 动没动：比较连续几帧同一区域的差异
    diffs = []
    prev = None
    for s in shots:
        c = s.convert("RGB").crop(box).resize((64, 64))
        data = list(c.getdata())
        if prev is not None:
            d = sum(1 for a, b in zip(prev, data) if abs(a[0]-b[0]) + abs(a[1]-b[1]) + abs(a[2]-b[2]) > 12)
            diffs.append(d / len(data))
        prev = data
    print("连续帧差异比例:", [f"{d:.1%}" for d in diffs])
    print("→ 在动吗:", "是（画面在变化）" if max(diffs) > 0.01 else "看起来是静止的")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
