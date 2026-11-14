# -*- coding: utf-8 -*-
"""把一段语音推给球并确认它真的在播放（不靠耳朵）"""
import json
import time
import urllib.request

import websocket


def say(text):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request("http://127.0.0.1:8798/say", data=body,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode())


def main():
    r = say("我现在会说话了，你听到了吗？")
    print("合成:", r.get("ok"), "url长度", len(r.get("url", "")))
    if not r.get("ok"):
        print("失败:", r.get("why"))
        return 1

    targets = json.loads(urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=6).read())
    page = next((x for x in targets if x.get("type") == "page"
                 and "pet.html" in (x.get("url") or "")), None)
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
    n = [0]

    def ev(expr):
        n[0] += 1
        i = n[0]
        ws.send(json.dumps({"id": i, "method": "Runtime.evaluate",
                            "params": {"expression": expr, "returnByValue": True,
                                       "awaitPromise": True}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == i:
                res = (m.get("result") or {}).get("result", {})
                return res.get("value"), m.get("error") or res.get("description")

    url_literal = json.dumps(r["url"])
    v, err = ev(f'window.pet.speakDataUrl({url_literal}).then(function(d){{return "ok "+d.toFixed(1)+"s";}})')
    print("推送:", v, err)

    for i in range(5):
        time.sleep(0.8)
        d, _ = ev("JSON.stringify(window.pet.debug())")
        print(f"  +{(i+1)*0.8:.1f}s {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
