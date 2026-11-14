# -*- coding: utf-8 -*-
"""验证：说话时嘴部变化是否只局限在嘴附近

播放一段真实语音，连拍多帧，统计每帧相对「静默帧」的变化区域，
看 bbox 是否集中在嘴的位置（而不是整张脸）。
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


def synth(text):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request("http://127.0.0.1:8798/say", data=body,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode())


def main():
    c = Cdp()
    print("1) 先拍静默帧")
    c.ev("window.pet.stop()")
    time.sleep(1.2)
    idle = c.shot("mouth-idle.png")

    print("2) 合成并播放一段话")
    r = synth("大家好，我是大肥鱼一号，现在正在说话。")
    if not r.get("ok"):
        print("合成失败:", r.get("why"))
        return 1
    url_lit = json.dumps(r["url"])
    c.ev(f'window.pet.speakDataUrl({url_lit})')

    print("3) 播放中连拍 6 帧")
    shots = []
    for i in range(6):
        time.sleep(0.45)
        p = c.shot(f"mouth-talk-{i}.png")
        d, _ = c.ev("JSON.stringify(window.pet.debug())")
        print(f"   frame{i}: {d}")
        if p:
            shots.append(p)

    if not idle or not shots:
        print("截图失败")
        return 1

    base = Image.open(idle).convert("RGB")
    W, H = base.size
    print(f"\n画面 {W}x{H}，逐帧对比静默帧：")
    best = None
    for i, p in enumerate(shots):
        im = Image.open(p).convert("RGB")
        diff = ImageChops.difference(base, im).convert("L")
        bbox = diff.getbbox()
        hist = diff.histogram()
        ch = sum(hist[30:])
        ratio = ch / (W * H)
        if bbox:
            bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
            print(f"  frame{i}: {ratio:.2%} 变化  bbox={bbox} ({bw}x{bh})")
            if best is None or ratio > best[1]:
                best = (i, ratio, bbox)
        else:
            print(f"  frame{i}: 无变化")

    if best:
        i, ratio, bbox = best
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        print(f"\n最大变化帧 frame{i}: {ratio:.2%}, 区域 {bw}x{bh}")
        if bw > W * 0.6 or bh > H * 0.6:
            print("→ ⚠ 变化覆盖大半个画面：嘴动会牵动整张脸")
        else:
            print("→ ✓ 变化局限在局部，嘴动不会扭曲全脸")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
