# -*- coding: utf-8 -*-
"""精确定位嘴：用 rig 的 face.mouth 坐标 + 页面的实际视图变换，算出嘴在球里的像素位置"""
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
        t = json.loads(urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=5).read())
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
        r = self.call("Page.captureScreenshot", {"format": "png"}, wait=15)
        d = (r.get("result") or {}).get("data")
        if not d:
            return None
        p = OUT / name
        p.write_bytes(base64.b64decode(d))
        return p


def main():
    c = Cdp()
    # 让页面自己算出「源图坐标 -> 屏幕坐标」的映射
    expr = """
    (() => {
      if (!window.__dbgAvatar) return 'no avatar';
      const av = window.__dbgAvatar;
      const v = av.getViewport();
      const cv = document.querySelector('#avatar');
      const k = cv.clientWidth / v.width;
      const map = (x, y) => [ (x * v.scale + v.offset[0]) * k, (y * v.scale + v.offset[1]) * k ];
      const mouth = window.__dbgRig && window.__dbgRig.face ? window.__dbgRig.face.mouth : null;
      return JSON.stringify({viewport: v, k, mouth, mapped: mouth ? map(mouth.cx, mouth.cy) : null});
    })()
    """
    v, err = c.ev(expr)
    print("映射:", v, err)

    # 用 setMouth 冻结，取两帧
    def hold(m, secs=0.9):
        t0 = time.time()
        while time.time() - t0 < secs:
            c.ev(f"window.pet.setMouth({m})")
            time.sleep(0.18)

    hold(0.0, 1.0)
    a = c.shot("mm-closed.png")
    hold(1.0, 1.0)
    b = c.shot("mm-open.png")
    hold(0.0, 0.3)

    if not (a and b):
        print("截图失败")
        return 1

    data = json.loads(v) if v and v.startswith("{") else None
    if data and data.get("mapped"):
        mx, my = data["mapped"]
        print(f"嘴在球里的位置 ≈ ({mx:.0f},{my:.0f})")
        box = (max(0, int(mx) - 45), max(0, int(my) - 35), int(mx) + 45, int(my) + 35)
    else:
        box = (110, 110, 250, 210)
        print("拿不到映射，用默认区域", box)

    ia = Image.open(a).convert("RGB")
    ib = Image.open(b).convert("RGB")
    print("帧尺寸", ia.size, "检测区域", box)
    ca, cb = ia.crop(box), ib.crop(box)
    diff = ImageChops.difference(ca, cb).convert("L")
    hist = diff.histogram()
    changed = sum(hist[10:])
    total = ca.size[0] * ca.size[1]
    print(f"嘴部区域差异: {changed}/{total} = {changed/total:.2%}")
    print("→ 嘴动了吗:", "动了 ✓" if changed / total > 0.02 else "没动 ✗")

    ca.resize((ca.width * 3, ca.height * 3)).save(OUT / "mouth-closed-zoom.png")
    cb.resize((cb.width * 3, cb.height * 3)).save(OUT / "mouth-open-zoom.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
