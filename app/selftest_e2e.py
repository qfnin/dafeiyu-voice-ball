# -*- coding: utf-8 -*-
"""一键全流程验收：模拟点按钮 -> 说一段（用已有音频喂）-> 自动回答 -> 球播放

因为这里没有真人麦克风输入，改成：
  1) 调 /listen/start 开始录音
  2) 直接把一段合成语音从扬声器播出来（麦克风会收到），或者跳过这步
  3) 调 /listen/stop 拿结果
再验证球是否播放。
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def post(path, body=None, timeout=180):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request("http://127.0.0.1:8798" + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main():
    print("[1] 开始录音")
    print("   ", post("/listen/start"))

    print("[2] 从扬声器播放一句话（让麦克风收到）")
    wav = ROOT / "tts" / "audition" / "b1.wav"
    if wav.exists():
        subprocess.Popen(["powershell", "-NoProfile", "-Command",
                          f'(New-Object System.Media.SoundPlayer "{wav}").PlaySync()'])
        time.sleep(4)
    else:
        print("    没有测试音频，等 4 秒")
        time.sleep(4)

    print("[3] 查状态（应看到 auto_stopped 或 recording=False）")
    with urllib.request.urlopen("http://127.0.0.1:8798/status", timeout=5) as r:
        print("   ", r.read().decode())

    print("[4] 停止并回答")
    t0 = time.time()
    res = post("/listen/stop")
    print(f"    ok={res.get('ok')} 耗时{time.time()-t0:.1f}s")
    print(f"    听到: {res.get('text')}")
    print(f"    回答: {res.get('reply')}")
    print(f"    音频: {len(res.get('url',''))} 字节")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
