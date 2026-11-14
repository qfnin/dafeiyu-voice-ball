# -*- coding: utf-8 -*-
"""诊断按钮：打印球窗口的真实几何、按钮在页面里的位置，以及点击会落在哪个元素上"""
import json
import urllib.request

import websocket

# 页面里问：按钮的 bounding rect、elementFromPoint 命中什么
JS = """
(() => {
  const b = document.querySelector('#call');
  if (!b) return 'no button';
  const r = b.getBoundingClientRect();
  const cx = r.left + r.width/2, cy = r.top + r.height/2;
  const hit = document.elementFromPoint(cx, cy);
  const cs = getComputedStyle(b);
  return JSON.stringify({
    rect: [r.left|0, r.top|0, r.width|0, r.height|0],
    center: [cx|0, cy|0],
    hitTag: hit ? (hit.id || hit.tagName) : null,
    opacity: cs.opacity,
    pointerEvents: cs.pointerEvents,
    display: cs.display,
    zIndex: cs.zIndex,
    winSize: [innerWidth, innerHeight],
    bodyClass: document.body.className,
    hasShell: !!window.ballShell,
    ballRect: (() => { const q=document.querySelector('#ball').getBoundingClientRect(); return [q.left|0,q.top|0,q.width|0,q.height|0]; })(),
  });
})()
"""


def main():
    targets = json.loads(urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=6).read())
    page = next((x for x in targets if x.get("type") == "page"
                 and "pet.html" in (x.get("url") or "")), None)
    if not page:
        print("没有页面")
        return 1
    print("页面:", page.get("url"))
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=25)
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": JS, "returnByValue": True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == 1:
            v = (m.get("result") or {}).get("result", {}).get("value")
            print("按钮诊断:", v)
            if v and v.startswith("{"):
                d = json.loads(v)
                cx, cy = d["center"]
                print(f"\n按钮中心（页面坐标）: ({cx}, {cy})")
                print(f"命中元素: {d['hitTag']}")
                if d["hitTag"] not in ("call",):
                    print("  ⚠ 按钮被别的元素挡住了！")
                print(f"opacity={d['opacity']} pointerEvents={d['pointerEvents']} display={d['display']} zIndex={d['zIndex']}")
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
