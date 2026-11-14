# -*- coding: utf-8 -*-
"""逐帧检查嘴部形变：固定其他参数，只改 mouthOpen，量出形变范围

目的：判断「嘴动得奇怪」是形变过大、还是位置不对、还是整张脸都在动。
"""
import base64
import json
import time
import urllib.request
from pathlib import Path

import websocket
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs"


class Cdp:
    def __init__(self):
        t = json.loads(urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=6).read())
        url = next((x["webSocketDebuggerUrl"] for x in t
                    if x.get("type") == "page" and "pet.html" in (x.get("url") or "")), None)
        if not url:
            raise SystemExit("没有页面")
        self.ws = websocket.create_connection(url, timeout=25)
        self.n = 0

    def call(self, m, p=None, wait=20):
        self.n += 1
        i = self.n
        self.ws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
        t0 = time.time()
        while time.time() - t0 < wait:
            try:
                r = json.loads(self.ws.recv())
            except Exception as e:
                return {"err": str(e)}
            if r.get("id") == i:
                return r
        return {"err": "timeout"}

    def ev(self, expr):
        r = self.call("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True, "awaitPromise": True})
        res = (r.get("result") or {}).get("result", {})
        return res.get("value"), r.get("error") or res.get("description")

    def shot(self, name):
        self.call("Page.enable")
        r = self.call("Page.captureScreenshot", {"format": "png"}, wait=20)
        d = (r.get("result") or {}).get("data")
        if not d:
            return None
        p = OUT / name
        p.write_bytes(base64.b64decode(d))
        return p


def main():
    c = Cdp()
    # 关掉自动待机动作，只留嘴
    print("冻结自动动作…")
    c.ev("window.__freezeAll = true")

    frames = {}
    for v in (0.0, 0.3, 0.6, 1.0):
        # 持续喂同一个值，保持冻结
        for _ in range(6):
            c.ev(f"window.pet.setMouth({v})")
            time.sleep(0.12)
        p = c.shot(f"mouth-v{v}.png")
        frames[v] = p
        print(f"  mouthOpen={v} -> {p}")

    base = Image.open(frames[0.0]).convert("RGB")
    W, H = base.size
    print(f"\n画面 {W}x{H}")

    for v in (0.3, 0.6, 1.0):
        im = Image.open(frames[v]).convert("RGB")
        diff = ImageChops.difference(base, im).convert("L")
        bbox = diff.getbbox()
        hist = diff.histogram()
        changed = sum(hist[25:])          # 只算明显变化
        ratio = changed / (W * H)
        print(f"\nmouthOpen={v}: 明显变化像素 {changed} ({ratio:.2%})")
        if bbox:
            bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
            cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
            print(f"  变化区域 bbox={bbox} 尺寸 {bw}x{bh}")
            print(f"  中心 ({cx:.0f},{cy:.0f}) → 相对位置 x={cx/W:.0%} y={cy/H:.0%}")
            if bw > W * 0.5 or bh > H * 0.5:
                print("  ⚠ 变化区域超过画面一半，说明形变波及整张脸（这就是「奇怪」的原因）")

    # 把嘴部区域放大存下来，方便对比
    for v in (0.0, 1.0):
        im = Image.open(frames[v])
        crop = im.crop((int(W * 0.30), int(H * 0.28), int(W * 0.70), int(H * 0.62)))
        crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
        crop.save(OUT / f"mouth-zoom-{v}.png")
    print("\n嘴部放大图: logs/mouth-zoom-0.0.png / mouth-zoom-1.0.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
