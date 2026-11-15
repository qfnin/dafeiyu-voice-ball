"""语音对话桥（单句 + 通话双模式）

接口（只监听 127.0.0.1:8798）：
  GET  /ping            健康检查
  GET  /status          通话状态
  POST /ask/start       单句模式：听一句 -> 答一句 -> 自动回待机（球上点一下用这个）
  POST /call/start      接通（开始持续对话循环，备用）
  POST /call/stop       挂断（也用来中断单句）
  GET  /next            外壳轮询：有新回答就返回 {url, reply, text}
  POST /say             直接说一句（调试）
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voice_engine as ve

PORT = 8798
ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "bridge.log"


def log(*parts):
    import time
    line = time.strftime("%H:%M:%S") + "  " + " ".join(str(p) for p in parts)
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send({"ok": True})

    def do_GET(self):
        if self.path.startswith("/ping"):
            return self._send({"ok": True, "voice": ve.cfg().get("voice"), "mode": "once"})
        if self.path.startswith("/status"):
            return self._send(ve.status())
        if self.path.startswith("/next"):
            item = ve.pop_reply()
            return self._send(item or {"type": "idle"})
        self._send({"ok": False, "why": "unknown"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            data = {}

        if self.path.startswith("/ask/start"):
            log("单句对话")
            return self._send(ve.ask_once())
        if self.path.startswith("/call/start"):
            log("接通")
            return self._send(ve.call_start())
        if self.path.startswith("/call/stop"):
            log("挂断")
            return self._send(ve.call_stop())
        if self.path.startswith("/say"):
            text = data.get("text", "")
            try:
                url = ve.speak_text(text)
                return self._send({"ok": True, "url": url, "text": text})
            except Exception as exc:
                return self._send({"ok": False, "why": str(exc)})
        self._send({"ok": False, "why": "unknown"}, 404)

    def log_message(self, *args):
        pass


def main():
    log("语音桥（通话版）启动 127.0.0.1:", PORT)
    threading.Thread(target=ve.warmup, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
