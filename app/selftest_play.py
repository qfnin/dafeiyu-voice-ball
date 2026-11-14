# -*- coding: utf-8 -*-
"""验证球能播放语音（不靠耳朵）+ 检查人物在圆里的位置

播放验证：调用 /say 拿到 data URL，推给页面，读 pet.debug() 的 playing/speaking/envLen。
位置验证：抓页面截图，找「肤色像素」的重心，看它在圆的什么高度。
"""
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

import websocket
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs"


class Cdp:
    def __init__(self):
        t = json.loads(urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=6).read())
        url = next((x["webSocketDebuggerUrl"] for x in t
                    if x.get("type") == "page" and "pet.html" in (x.get("url") or "")), None)
        if not url:
            raise SystemExit("没有 pet 页面")
        self.ws = websocket.create_connection(url, timeout=30)
        self.n = 0

    def call(self, m, p=None, wait=25):
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


def skin_center(png):
    im = Image.open(png).convert("RGB")
    w, h = im.size
    px = im.load()
    xs, ys, n = 0, 0, 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            if r > 195 and g > 155 and b > 140 and r >= b - 12 and (r - b) < 70:
                xs += x
                ys += y
                n += 1
    if not n:
        return None
    return xs / n, ys / n, n, (w, h)


def main():
    c = Cdp()
    print("页面:", c.ev("location.href")[0])

    print("\n[A] 人物位置")
    p = c.shot("check-pos.png")
    if p:
        sc = skin_center(p)
        if sc:
            cx, cy, n, (w, h) = sc
            print(f"  画面 {w}x{h}，肤色像素 {n}")
            print(f"  肤色重心 = ({cx:.0f}, {cy:.0f}) → 纵向占比 {cy/h:.1%}")
            print(f"  → 脸的位置:", "偏上/居中（好）" if cy / h < 0.52 else "偏下（需要上提）")
        else:
            print("  没检测到肤色")

    print("\n[B] 播放验证")
    # 直接合成一句，推给页面
    data = json.dumps({"text": "测试播放，一二三四五六七八。"}).encode()
    req = urllib.request.Request("http://127.0.0.1:8798/say", data=data,
                                 headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
    print("  合成:", "成功" if r.get("ok") else r.get("why"))
    if not r.get("ok"):
        return 1
    url = r["url"]
    v, err = c.ev(f'window.pet.speakDataUrl({json.dumps(url)}).then(d=>"播放中 "+d.toFixed(1)+"s")')
    print("  推送:", v, err)
    for i in range(6):
        time.sleep(0.8)
        d, _ = c.ev("JSON.stringify(window.pet.debug())")
        print(f"   +{(i+1)*0.8:.1f}s {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
