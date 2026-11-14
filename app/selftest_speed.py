# -*- coding: utf-8 -*-
"""测各环节耗时，找出延迟大头"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ["HF_HOME"] = str(ROOT / "models" / "hf")
os.environ["HF_HUB_CACHE"] = str(ROOT / "models" / "hf" / "hub")
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import voice_engine as ve

WAV = ROOT / "tts" / "audition" / "b1.wav"


def t(label, fn, *a):
    t0 = time.time()
    r = fn(*a)
    dt = time.time() - t0
    print(f"  {label:22s} {dt:5.2f}s   {str(r)[:40]}")
    return r, dt


def main():
    print("=== 各环节耗时 ===")

    # 1) 首次加载
    t0 = time.time()
    ve.get_whisper()
    print(f"  {'Whisper 加载(首次)':22s} {time.time()-t0:5.2f}s")

    # 2) 识别
    for i in range(2):
        t(f"识别 small (第{i+1}次)", ve.transcribe, WAV)

    # 3) 大模型
    for i in range(2):
        t(f"Ollama 回答 (第{i+1}次)", ve.ask_llm, "你好呀，今天过得怎么样？")

    # 4) 合成
    for i in range(2):
        t(f"edge-tts 合成 (第{i+1}次)", ve.speak_text, "好的，我知道了，那我们继续聊吧。")

    print("\n=== 对比：更小的 whisper 模型 ===")
    for name in ("tiny", "base"):
        try:
            t0 = time.time()
            from faster_whisper import WhisperModel
            m = WhisperModel(name, device="cpu", compute_type="int8",
                             download_root=str(ROOT / "models" / "whisper"))
            load = time.time() - t0
            t0 = time.time()
            segs, info = m.transcribe(str(WAV), language="zh", beam_size=1,
                                      vad_filter=True, initial_prompt="以下是普通话的句子。")
            text = "".join(s.text for s in segs).strip()
            dt = time.time() - t0
            print(f"  {name:8s} 加载{load:5.2f}s  识别{dt:5.2f}s  -> {text[:35]}")
        except Exception as exc:
            print(f"  {name}: 失败 {str(exc)[:60]}")


if __name__ == "__main__":
    main()
