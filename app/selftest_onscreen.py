# -*- coding: utf-8 -*-
"""不看图也能验收：整屏抓图，扫描「圆球的特征色」出现在屏幕的什么位置。

圆球特征：
  - 深蓝底 #1a1f38 / #12162a（R,G,B 都小、B 略大）
  - 蓝色圆环 #7ea7ff（B 高、R/G 中高）
  - 角色肤色
如果屏幕右上方某处出现一坨这样的像素，并且轮廓接近正圆，就说明球真的显示出来了。
"""
import sys
from pathlib import Path

from PIL import ImageGrab

OUT = Path(__file__).resolve().parents[1] / "logs"


def main():
    img = ImageGrab.grab(all_screens=True)
    img.save(OUT / "screen-full.png")
    w, h = img.size
    print(f"整屏 {w}x{h}")

    rgb = img.convert("RGB")
    # 缩小 4 倍加速扫描，同时保留位置信息
    small = rgb.resize((w // 4, h // 4))
    sw, sh = small.size
    px = small.load()

    def is_ball_color(r, g, b):
        navy = r < 70 and g < 80 and 40 <= b <= 130 and b > r + 10
        ring = 100 <= r <= 160 and 140 <= g <= 190 and b >= 210
        return navy or ring

    # 统计每个 8x8 小格里的球色像素比例，找出最密集的一块
    cell = 8
    best = []
    for cy in range(0, sh - cell, cell):
        for cx in range(0, sw - cell, cell):
            hit = 0
            for y in range(cy, cy + cell):
                for x in range(cx, cx + cell):
                    r, g, b = px[x, y]
                    if is_ball_color(r, g, b):
                        hit += 1
            if hit > cell * cell * 0.55:
                best.append((hit, cx * 4, cy * 4))

    print(f"球色密集小格数: {len(best)}")
    if best:
        xs = [b[1] for b in best]
        ys = [b[2] for b in best]
        print(f"密集区域范围: x {min(xs)}..{max(xs)+cell*4}, y {min(ys)}..{max(ys)+cell*4}")
        print(f"粗估球直径: {max(max(xs)-min(xs), max(ys)-min(ys)) + cell*4} px")
    else:
        print("屏幕上没有找到球色区域")

    # 顺便看看整屏最常见的几种颜色，判断球是不是被别的窗口挡住了
    from collections import Counter
    top = Counter(list(small.getdata())).most_common(4)
    print("全屏最常见颜色:", top)


if __name__ == "__main__":
    sys.exit(main())
