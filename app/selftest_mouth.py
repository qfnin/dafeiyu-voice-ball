# -*- coding: utf-8 -*-
"""测嘴型：把 mouthOpen 强行设成 0 / 1，各截一帧，看嘴部区域有没有变化

如果两帧一模一样，说明：
  a) 绑定里没有嘴的网格，或
  b) 嘴型被别的参数盖住了，或
  c) 我们看到的嘴太小，像素级差异看不出来
"""
import base64
import json
import time
import urllib.request
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs"


class Cdp:
    def __init__(self):
        targets = json.loads(urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=5).read())
        url = next((t["webSocketDebuggerUrl"] for t in targets
                    if t.get("type") == "page" and "pet.html" in (t.get("url") or "")), None)
        if not url:
            raise SystemExit("没有 pet 页面")
        self.ws = websocket.create_connection(url, timeout=25)
        self.n = 0

    def call(self, method, params=None, wait=20):
        self.n += 1
        i = self.n
        self.ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
        t0 = time.time()
        while time.time() - t0 < wait:
            try:
                m = json.loads(self.ws.recv())
            except Exception as exc:
                return {"err": str(exc)}
            if m.get("id") == i:
                return m
        return {"err": "timeout"}

    def ev(self, expr):
        r = self.call("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True, "awaitPromise": True})
        res = (r.get("result") or {}).get("result", {})
        return res.get("value"), r.get("error") or res.get("description")

    def shot(self, name):
        self.call("Page.enable")
        r = self.call("Page.captureScreenshot", {"format": "png"}, wait=15)
        data = (r.get("result") or {}).get("data")
        if not data:
            return None
        p = OUT / name
        p.write_bytes(base64.b64decode(data))
        return p


def main():
    c = Cdp()
    print("页面:", c.ev("location.href")[0])
    print("rig 里有没有嘴:", c.ev("JSON.stringify({mouth:!!(window.__rig&&window.__rig.mouth),"
                                  "hasPet:!!window.pet})")[0])

    # 1) 冻结自动动作，手动控 mouthOpen
    c.ev("window.__freeze=true")
    # 关掉 requestAnimationFrame 对参数的覆盖：直接改 avatar 的参数
    print("\n[1] mouthOpen = 0")
    c.ev("window.pet.setMouth ? window.pet.setMouth(0) : 'no setMouth'")
    time.sleep(1.0)
    a = c.shot("mouth-0.png")

    print("[2] mouthOpen = 1")
    c.ev("window.pet.setMouth ? window.pet.setMouth(1) : 'no setMouth'")
    time.sleep(1.0)
    b = c.shot("mouth-1.png")

    print("[3] mouthOpen = 0.5")
    c.ev("window.pet.setMouth ? window.pet.setMouth(0.5) : 'no setMouth'")
    time.sleep(0.8)
    d = c.shot("mouth-05.png")

    c.ev("window.pet.setMouth ? window.pet.setMouth(0) : 0")

    if not (a and b):
        print("截图失败")
        return 1

    from PIL import Image, ImageChops
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    diff = ImageChops.difference(ia, ib).convert("L")
    bbox = diff.getbbox()
    hist = diff.histogram()
    changed = sum(hist[12:])
    total = ia.size[0] * ia.size[1]
    print(f"\n两帧差异: {changed} px = {changed/total:.2%}, bbox={bbox}")
    if bbox:
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        print(f"变化区域 {bw}x{bh} 位置 {bbox[:2]}")
    print("→ 嘴型可见形变:", "有" if changed / total > 0.002 else "几乎没有")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
