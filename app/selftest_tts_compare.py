# -*- coding: utf-8 -*-
"""对比 edge-tts 和 Windows 本地 SAPI 的速度

结论用来决定悬浮球用哪个合成引擎。
"""
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TTS = ROOT / "tts"
TTS.mkdir(parents=True, exist_ok=True)

TEXT = "主人好呀，我是大肥鱼1号"

PS = """
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = 2
$sw = [Diagnostics.Stopwatch]::StartNew()
$s.SetOutputToWaveFile("{out}")
$s.Speak("{text}")
$s.Dispose()
Write-Output $sw.ElapsedMilliseconds
"""


def sapi(text, out):
    script = PS.format(out=str(out).replace("\\", "\\\\"), text=text)
    t0 = time.time()
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                       capture_output=True, text=True, timeout=60)
    dt = time.time() - t0
    ok = out.exists() and out.stat().st_size > 1000
    return dt, ok, (r.stdout or "").strip(), (r.stderr or "")[:100]


def edge(text):
    import asyncio
    import sys
    sys.path.insert(0, str(ROOT / "app"))
    import edge_tts

    async def go():
        buf = bytearray()
        comm = edge_tts.Communicate(text, "zh-CN-XiaoyiNeural", rate="+10%", pitch="+30Hz")
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        return len(buf)

    t0 = time.time()
    n = asyncio.run(go())
    return time.time() - t0, n


def main():
    print(f"测试文本: {TEXT}\n")

    print("=== Windows SAPI（本地，离线）===")
    for i in range(2):
        out = TTS / f"sapi-{i}.wav"
        dt, ok, ms, err = sapi(TEXT, out)
        print(f"  第{i+1}次: {dt:.2f}s  文件{'OK' if ok else '失败'}  {ms}ms  {err}")

    print("\n=== edge-tts（联网）===")
    for i in range(2):
        dt, n = edge(TEXT)
        print(f"  第{i+1}次: {dt:.2f}s  {n} 字节")


if __name__ == "__main__":
    main()
