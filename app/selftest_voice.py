# -*- coding: utf-8 -*-
"""验证：语音桥能不能完整跑通「识别 -> 大模型 -> 合成」

不依赖麦克风：直接把一段已知音频塞给识别环节，再走完 LLM 和 TTS。
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ["HF_HOME"] = str(ROOT / "models" / "hf")
os.environ["HF_HUB_CACHE"] = str(ROOT / "models" / "hf" / "hub")
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


def post(path, body=None, timeout=180):
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:8798" + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    print("1) /ping")
    with urllib.request.urlopen("http://127.0.0.1:8798/ping", timeout=5) as r:
        print("  ", r.read().decode())

    print("2) 直接测「合成」：POST /say")
    t0 = time.time()
    r = post("/say", {"text": "你好呀，我是大肥鱼1号，很高兴认识你！"})
    print(f"   ok={r.get('ok')} 耗时 {time.time()-t0:.1f}s url长度={len(r.get('url',''))}")

    print("3) 测「大模型」：直接问一句")
    import voice_engine as ve
    t0 = time.time()
    reply = ve.ask_llm("你是谁呀？")
    print(f"   回答：{reply}  ({time.time()-t0:.1f}s)")

    print("4) 测「合成回答」")
    t0 = time.time()
    url = ve.speak_text(reply)
    print(f"   合成完成 {time.time()-t0:.1f}s，url 长度 {len(url)}")

    print("\n全部环节通过 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
