# -*- coding: utf-8 -*-
"""给悬浮球做一个圆形图标：深海蓝底 + 鲸鱼娘头像 + 蓝色光环"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(os.environ.get("RUIC_HOME") or (ROOT.parent / "RuiC-2D")) / "projects" / "da-fei-yu-1" / "previews" / "head.png"
OUT_ICO = ROOT / "assets" / "ball.ico"
OUT_PNG = ROOT / "assets" / "ball-icon.png"
OUT_ICO.parent.mkdir(parents=True, exist_ok=True)

S = 512


def rounded_head(head: Image.Image) -> Image.Image:
    """把头部裁成合适的构图"""
    bbox = head.getbbox()
    if bbox:
        head = head.crop(bbox)
    return head


def main():
    head = Image.open(SRC).convert("RGBA")
    head = rounded_head(head)

    # 底板：深海蓝渐变圆
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / S
        r = int(18 + t * 18)
        g = int(24 + t * 26)
        b = int(48 + t * 40)
        gd.line([(0, y), (S, y)], fill=(r, g, b, 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse((4, 4, S - 5, S - 5), fill=255)
    base.paste(grad, (0, 0), mask)

    # 内发光：底部蓝色晕
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        (int(S * 0.15), int(S * 0.55), int(S * 0.85), int(S * 1.15)),
        fill=(110, 165, 255, 90),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    base.alpha_composite(glow)

    # 放头像：宽度占 86%，底部对齐到圆的 96%
    inner = int(S * 0.86)
    scale = min(inner / head.width, inner / head.height)
    hw, hh = int(head.width * scale), int(head.height * scale)
    head2 = head.resize((hw, hh), Image.LANCZOS)
    cx = (S - hw) // 2
    cy = int(S * 0.96) - hh
    if cy < 10:
        cy = (S - hh) // 2
    base.alpha_composite(head2, (cx, cy))

    # 蓝色光环
    ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse((5, 5, S - 6, S - 6), outline=(126, 167, 255, 255), width=11)
    rd.ellipse((16, 16, S - 17, S - 17), outline=(90, 130, 220, 110), width=3)
    base.alpha_composite(ring)

    # 裁成正圆
    final_mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(final_mask).ellipse((5, 5, S - 6, S - 6), fill=255)
    base.putalpha(final_mask)

    base.save(OUT_PNG)
    base.save(OUT_ICO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("图标已生成:")
    print(" ", OUT_ICO, f"{OUT_ICO.stat().st_size} 字节")
    print(" ", OUT_PNG)


if __name__ == "__main__":
    main()
