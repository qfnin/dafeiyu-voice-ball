# -*- coding: utf-8 -*-
"""嘴型专项：只冻结「非嘴部」参数，单独变化 mouthOpen，看嘴部区域差异

上一版测出来的 23% 差异是全画面（自动动作/呼吸也在动），不能证明嘴在动。
这里先让页面进入「冻结」状态：固定 angleX/Y/Z、breath，只改 mouthOpen。
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


def region_diff(a, b, box):
    ia = Image.open(a).convert("RGB").crop(box)
    ib = Image.open(b).convert("RGB").crop(box)
    diff = ImageChops.difference(ia, ib).convert("L")
    hist = diff.histogram()
    changed = sum(hist[12:])
    total = ia.size[0] * ia.size[1]
    return changed / total, diff.getbbox()


def main():
    c = Cdp()
    print("注入冻结：固定所有非嘴部参数")
    c.ev("""
      window.__origAdvance = window.__origAdvance || null;
      window.__freezeLoop = true;
      // 直接接管：每帧只设固定参数 + 指定 mouthOpen
      window.__setMouthOnly = (m) => {
        window.__mouthTarget = m;
      };
      'ok'
    """)
    print(c.ev("typeof window.__setMouthOnly")[0])

    # 用 pet.setMouth 已经能冻结 3 秒，这里连续调用保持冻结
    def hold(m, secs=0.8):
        t0 = time.time()
        while time.time() - t0 < secs:
            c.ev(f"window.pet.setMouth({m})")
            time.sleep(0.2)

    print("\n[1] 闭口")
    hold(0.0, 1.0)
    a = c.shot("m-closed.png")

    print("[2] 张口")
    hold(1.0, 1.0)
    b = c.shot("m-open.png")

    hold(0.0, 0.5)

    if not (a and b):
        print("截图失败")
        return 1

    W, H = Image.open(a).size
    print(f"\n整帧 {W}x{H}")
    whole, wbox = region_diff(a, b, (0, 0, W, H))
    print(f"整帧差异 {whole:.2%} bbox={wbox}")

    # 嘴大概在画面中下部：按 rig 的 face.mouth (cx 580, cy 451) / 1254 换算
    mx, my = int(W * 0.46), int(H * 0.40)
    box = (max(0, mx - 70), max(0, my - 50), min(W, mx + 70), min(H, my + 50))
    d, bbox = region_diff(a, b, box)
    print(f"嘴部区域 {box} 差异 {d:.2%} bbox={bbox}")
    print("→ 嘴部有可见变化:", "是" if d > 0.02 else "否（太小或没动）")

    Image.open(a).crop(box).resize((280, 200)).save(OUT / "m-closed-crop.png")
    Image.open(b).crop(box).resize((280, 200)).save(OUT / "m-open-crop.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
