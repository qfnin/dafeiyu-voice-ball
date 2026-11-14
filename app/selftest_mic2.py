# -*- coding: utf-8 -*-
"""麦克风排查：对每个设备用 sd.rec() 录 2 秒，打印真实 RMS，并把有声音的存成 wav

用法：运行后持续大声说话，脚本会挨个设备录。
"""
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

OUT = Path(__file__).resolve().parents[1] / "cache" / "rec"
OUT.mkdir(parents=True, exist_ok=True)
RATE = 16000


def main():
    devs = [(i, d) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
    seen = set()
    good = []
    print("请持续大声说话（约 20 秒）…\n")
    for i, d in devs:
        key = d["name"][:35]
        if key in seen:
            continue
        seen.add(key)
        try:
            rec = sd.rec(int(2.0 * RATE), samplerate=RATE, channels=1, dtype="int16",
                         device=i, blocking=True)
            arr = rec.astype(np.float64)
            rms = float(np.sqrt(np.mean(arr ** 2)))
            peak = int(np.max(np.abs(arr)))
            tag = ""
            if rms > 30:
                import wave
                p = OUT / f"dev{i}.wav"
                with wave.open(str(p), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(RATE)
                    wf.writeframes(rec.tobytes())
                tag = f"  -> 已存 {p.name}"
                good.append((i, d["name"], rms))
            print(f"[{i:2d}] {d['name'][:42]:44s} RMS={rms:8.1f} PEAK={peak:6d}{tag}")
        except Exception as exc:
            print(f"[{i:2d}] {d['name'][:42]:44s} 打不开: {str(exc)[:38]}")
        time.sleep(0.3)

    print("\n=== 有声音的设备 ===")
    if good:
        for i, name, rms in sorted(good, key=lambda x: -x[2]):
            print(f"  [{i}] {name}  RMS={rms:.1f}")
        best = max(good, key=lambda x: x[2])
        print(f"\n建议 input_device = {best[0]}  （{best[1]}）")
    else:
        print("  一个都没有。检查：麦克风是否被静音/占用、系统隐私设置是否允许桌面应用访问麦克风")


if __name__ == "__main__":
    main()
