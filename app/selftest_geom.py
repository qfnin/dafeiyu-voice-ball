# -*- coding: utf-8 -*-
"""检查悬浮球窗口的真实尺寸/位置，并抓一张页面图看构图"""
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parents[1]
CDP = "http://127.0.0.1:9334/json"


def page_ws():
    targets = json.loads(urllib.request.urlopen(CDP, timeout=5).read())
    for t in targets:
        if t.get("type") == "page" and "pet.html" in (t.get("url") or ""):
            return t["webSocketDebuggerUrl"]
    return None


def main():
    ws_url = page_ws()
    if not ws_url:
        print("没有 pet 页面")
        return
    ws = websocket.create_connection(ws_url, timeout=25)
    n = [0]

    def call(method, params=None, wait=25):
        n[0] += 1
        i = n[0]
        ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
        t0 = time.time()
        while time.time() - t0 < wait:
            try:
                msg = json.loads(ws.recv())
            except Exception as exc:
                return {"err": str(exc)}
            if msg.get("id") == i:
                return msg
        return {"err": "timeout"}

    def ev(expr):
        r = call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        res = (r.get("result") or {}).get("result", {})
        return res.get("value"), r.get("error") or res.get("description")

    print("页面几何:", ev("JSON.stringify({iw:innerWidth,ih:innerHeight,dpr:devicePixelRatio,"
                          "ow:outerWidth,oh:outerHeight,sx:screenX,sy:screenY,"
                          "ball:[ball.clientWidth,ball.clientHeight]})")[0])
    call("Page.enable")
    r = call("Page.captureScreenshot", {"format": "png"}, wait=15)
    data = ((r.get("result") or {}).get("data"))
    if data:
        out = ROOT / "logs" / "ball-live.png"
        out.write_bytes(base64.b64decode(data))
        print("已截图", out, len(data), "base64 字节")
    else:
        print("截图失败", r)


if __name__ == "__main__":
    main()
