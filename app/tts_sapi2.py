# -*- coding: utf-8 -*-
"""用 comtypes 直接调 Windows SAPI 合成（离线，约 0.3 秒）

比 PowerShell 方式可靠：中文直接用 Python str 传进去，不经过命令行编码。
"""
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "cache" / "tmp"
TMP.mkdir(parents=True, exist_ok=True)

_sp_voice = None


def _get_voice():
    global _sp_voice
    if _sp_voice is not None:
        return _sp_voice
    import comtypes.client
    _sp_voice = comtypes.client.CreateObject("SAPI.SpVoice")
    return _sp_voice


def synth(text: str, out_wav: Path, rate: int = 2, voice_name: str = "") -> tuple[bool, float]:
    """合成到 wav 文件，返回 (成功, 耗时)"""
    import comtypes.client
    t0 = time.time()
    try:
        voice = _get_voice()
        if voice_name:
            for v in voice.GetVoices():
                if voice_name in v.GetDescription():
                    voice.Voice = v
                    break
        voice.Rate = rate
        # 直接指定输出到文件（用 SpFileStream 的另一种构造方式）
        stream = comtypes.client.CreateObject("SAPI.SpFileStream")
        stream.Format.Type = 22          # SAFT22kHz16BitMono
        stream.Open(str(out_wav), 3, False)   # 3 = SSFMCreateForWrite
        old = voice.AudioOutputStream
        voice.AudioOutputStream = stream
        try:
            voice.Speak(text)
        finally:
            voice.AudioOutputStream = old
            stream.Close()
        ok = out_wav.exists() and out_wav.stat().st_size > 2000
        return ok, time.time() - t0
    except Exception as exc:
        print(f"  SAPI 错误: {exc}")
        return False, time.time() - t0


def list_voices():
    try:
        voice = _get_voice()
        return [v.GetDescription() for v in voice.GetVoices()]
    except Exception as exc:
        return [f"失败: {exc}"]


if __name__ == "__main__":
    print("可用语音:", list_voices())
    print()
    out = ROOT / "tts" / "sapi-demo.wav"
    text = "主人好呀，我是大肥鱼1号，今天想聊点什么？"
    for i in range(3):
        ok, dt = synth(text, out)
        size = out.stat().st_size if out.exists() else 0
        print(f"  第{i+1}次: {dt:.2f}s {'✓' if ok else '✗'}  {size} 字节")
    if out.exists() and out.stat().st_size > 2000:
        print("\n播放测试：")
        import subprocess
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f'(New-Object System.Media.SoundPlayer "{out}").PlaySync()'])
