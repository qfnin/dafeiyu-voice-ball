# -*- coding: utf-8 -*-
"""诊断通话按钮：为什么点不了

逐步排查：
  1. 按钮元素和事件是否绑上
  2. 派发 pointerdown 会不会触发通话
  3. 直接调 shell 接口能不能通
"""
import json
import time
import urllib.request

import websocket

JS_DISPATCH = (
    '(function(){'
    '  var b = document.querySelector("#call");'
    '  if (!b) return "no-button";'
    '  var ev = new PointerEvent("pointerdown", {bubbles:true, button:0, clientX:179, clientY:311});'
    '  try { b.dispatchEvent(ev); } catch (e) { return "dispatch-fail:" + e.message; }'
    '  return "dispatched";'
    '})()'
)

JS_STATE = (
    'JSON.stringify({'
    '  cls: (document.querySelector("#call")||{}).className,'
    '  text: (document.querySelector("#callState")||{}).textContent,'
    '  shell: typeof window.ballShell,'
    '  vs: window.ballShell ? typeof window.ballShell.voiceStart : "none",'
    '  onvs: window.ballShell ? typeof window.ballShell.onVoiceState : "none",'
    '  pet: window.pet ? window.pet.debug() : null'
    '})'
)


class Cdp:
    def __init__(self):
        t = json.loads(urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=6).read())
        page = [x for x in t if x.get("type") == "page" and "pet.html" in (x.get("url") or "")]
        if not page:
            raise SystemExit("没有 pet 页面")
        self.ws = websocket.create_connection(page[0]["webSocketDebuggerUrl"], timeout=25)
        self.n = 0

    def ev(self, expr, wait=15):
        self.n += 1
        i = self.n
        self.ws.send(json.dumps({"id": i, "method": "Runtime.evaluate",
                                 "params": {"expression": expr, "returnByValue": True,
                                            "awaitPromise": True}}))
        t0 = time.time()
        while time.time() - t0 < wait:
            try:
                m = json.loads(self.ws.recv())
            except Exception as exc:
                return f"<recv error: {exc}>"
            if m.get("id") == i:
                r = m.get("result") or {}
                if r.get("exceptionDetails"):
                    return f"<exception: {r['exceptionDetails'].get('text')}>"
                return (r.get("result") or {}).get("value")
        return "<timeout>"


def main():
    c = Cdp()
    print("初始状态:", c.ev(JS_STATE))

    print("\n派发 pointerdown…")
    print("  结果:", c.ev(JS_DISPATCH))
    time.sleep(2)
    print("  之后状态:", c.ev(JS_STATE))

    print("\n直接调 shell.voiceStart()…")
    print("  结果:", c.ev('(function(){try{window.ballShell.voiceStart();return "called";}catch(e){return "err:"+e.message}})()'))
    time.sleep(3)
    print("  之后状态:", c.ev(JS_STATE))

    print("\n直接调 shell.voiceStop()…")
    print("  结果:", c.ev('(function(){try{window.ballShell.voiceStop();return "called";}catch(e){return "err:"+e.message}})()'))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
