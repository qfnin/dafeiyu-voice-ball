# -*- coding: utf-8 -*-
"""录音自检：把每个输入设备都试一遍，看哪个能采到真实声音

用法：运行后对着麦克风说话，脚本会逐个设备录 1.5 秒并报电平。
"""
import sys
import time

import numpy as np
import sounddevice as sd

DUR = 1.5
SR = 16000


def probe(idx):
    try:
        data = sd.rec(int(DUR * SR), samplerate=SR, channels=1, dtype="int16", device=idx)
        sd.wait()
        rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
        peak = int(np.max(np.abs(data)))
        return rms, peak
    except Exception as exc:
        return None, str(exc)


def main():
    print(f"=== 逐个设备录 {DUR}s，请持续说话 ===")
    devs = [(i, d) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
    # 去重（同一设备可能有多个 host API 条目）
    seen = set()
    results = []
    for i, d in devs:
        key = d["name"][:40]
        if key in seen:
            continue
        seen.add(key)
        print(f"\n[{i}] {d['name'][:45]}  sr={d['default_samplerate']}")
        rms, peak = probe(i)
        if rms is None:
            print(f"    失败: {peak}")
            continue
        bar = "#" * min(40, int(rms / 50))
        print(f"    RMS={rms:7.1f}  PEAK={peak:5d}  {bar}")
        results.append((i, d["name"], rms, peak))

    print("\n=== 结论 ===")
    results.sort(key=lambda x: -x[2])
    for i, name, rms, peak in results:
        level = "有声音 ✓" if rms > 120 else ("很轻" if rms > 40 else "几乎无声")
        print(f"  [{i}] {name[:40]:42s} RMS={rms:7.1f}  {level}")
    if results:
        print(f"\n推荐设备: [{results[0][0]}] {results[0][1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
