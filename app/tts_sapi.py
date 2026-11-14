# -*- coding: utf-8 -*-
"""用 Windows SAPI 本地合成语音（离线，约 0.1 秒）

避开 PowerShell 的中文编码坑：把脚本写成 UTF-8 BOM 文件再执行。
"""
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "cache" / "tmp"
TMP.mkdir(parents=True, exist_ok=True)

PS_TEMPLATE = """$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{
  $s.Rate = {rate}
  $s.Volume = 100
  {voice_line}
  $s.SetOutputToWaveFile("{out}")
  $s.Speak("{text}")
}} finally {{
  $s.Dispose()
}}
Write-Output "OK"
"""


def synth_sapi(text: str, out_path: Path, rate: int = 2, voice: str = "") -> tuple[bool, float]:
    """用 SAPI 合成，返回 (成功, 耗时)"""
    out = str(out_path).replace("\\", "\\\\")
    voice_line = ""
    if voice:
        voice_line = f'$s.SelectVoice("{voice}")'
    script = PS_TEMPLATE.format(
        rate=rate,
        voice_line=voice_line,
        out=out,
        text=text.replace('"', '`"'),
    )
    script_file = TMP / f"sapi-{uuid.uuid4().hex[:8]}.ps1"
    # 写成 UTF-8 with BOM，PowerShell 5.1 才能正确读中文
    script_file.write_text(script, encoding="utf-8-sig")
    t0 = time.time()
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_file)],
            capture_output=True, timeout=60,
        )
        dt = time.time() - t0
        ok = out_path.exists() and out_path.stat().st_size > 2000
        return ok, dt
    except Exception as exc:
        return False, time.time() - t0
    finally:
        try:
            script_file.unlink()
        except OSError:
            pass


def list_voices():
    ps = ('Add-Type -AssemblyName System.Speech;'
          '(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | '
          'ForEach-Object { $_.VoiceInfo.Name }')
    f = TMP / "voices.ps1"
    f.write_text(ps, encoding="utf-8-sig")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(f)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    f.unlink(missing_ok=True)
    return [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]


if __name__ == "__main__":
    print("可用语音:", list_voices())
    print()
    out = ROOT / "tts" / "sapi-demo.wav"
    for i in range(3):
        ok, dt = synth_sapi("主人好呀，我是大肥鱼1号，今天想聊点什么？", out)
        print(f"  第{i+1}次: {dt:.2f}s {'✓' if ok else '✗'}")
    if out.exists():
        print(f"  文件: {out.stat().st_size} 字节")
