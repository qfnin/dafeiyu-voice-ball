# -*- coding: utf-8 -*-
"""端到端自检：页面几何 -> 触发说话 -> 观察口型包络是否在跑"""
import json
import time
import urllib.request

import websocket

CDP = "http://127.0.0.1:9334/json"


def page_ws():
    targets = json.loads(urllib.request.urlopen(CDP, timeout=5).read())
    for t in targets:
        if t.get("type") == "page" and "pet.html" in (t.get("url") or ""):
            return t["webSocketDebuggerUrl"], t.get("url")
    return None, None


class Cdp:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=25)
        self.n = 0

    def call(self, method, params=None, wait=25):
        self.n += 1
        i = self.n
        self.ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
        t0 = time.time()
        while time.time() - t0 < wait:
            try:
                msg = json.loads(self.ws.recv())
            except Exception as exc:
                return {"err": str(exc)}
            if msg.get("id") == i:
                return msg
        return {"err": "timeout"}

    def ev(self, expr):
        r = self.call("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True, "awaitPromise": True})
        res = (r.get("result") or {}).get("result", {})
        return res.get("value"), r.get("error") or res.get("description")


def main():
    ws_url, url = page_ws()
    if not ws_url:
        print("没有找到 pet 页面（CDP 9334）")
        return
    print("页面:", url[:90])
    c = Cdp(ws_url)
    v, err = c.ev("JSON.stringify({w:innerWidth,h:innerHeight,dpr:devicePixelRatio,"
                  "ball:[ball.clientWidth,ball.clientHeight],"
                  "shell:!!window.ballShell,pet:!!window.pet})")
    print("几何/状态:", v, err)

    v, err = c.ev("JSON.stringify(window.pet.debug())")
    print("初始 debug:", v, err)

    print("--- 触发说话 ---")
    v, err = c.ev('window.ballShell.speak("你好，我是大肥鱼1号，现在会说话啦。")'
                  '.then(u=>u?("ok "+u.length):"empty")')
    print("speak 结果:", v, err)

    for i in range(7):
        time.sleep(1)
        d, _ = c.ev("JSON.stringify(window.pet.debug())")
        print(f"  +{i+1}s", d)


if __name__ == "__main__":
    main()
