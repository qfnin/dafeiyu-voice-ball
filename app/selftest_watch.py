# -*- coding: utf-8 -*-
"""验证「点按钮 -> 开始录音 -> 录音里有声音」

用法：运行后，用鼠标点球上的电话按钮（或按空格），然后对着麦克风说话。
脚本会盯着 voice.log 和 status 接口，确认录音真的开始了、而且采到了声音。
"""
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "voice.log"


def status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8798/status", timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as exc:
        return {"error": str(exc)}


def main():
    print("请现在：点球上的蓝色电话按钮（或按空格），然后对着麦克风说话。")
    print("我会观察 25 秒，看录音状态。\n")
    t0 = time.time()
    last = None
    while time.time() - t0 < 25:
        s = status()
        key = (s.get("recording"), s.get("busy"), s.get("error"))
        if key != last:
            print(f"  +{time.time()-t0:4.1f}s  recording={s.get('recording')}  busy={s.get('busy')}  err={s.get('error','')!r}")
            last = key
        time.sleep(0.5)
    print("\n=== voice.log 末尾 ===")
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]:
            print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
