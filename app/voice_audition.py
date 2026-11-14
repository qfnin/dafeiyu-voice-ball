# -*- coding: utf-8 -*-
"""生成「大肥鱼」风格的候选音色，拼成一条试听文件

思路：edge-tts 的中文音色里，最接近抖音萌系 VTuber 的是
  - zh-CN-XiaoyiNeural（官方标注 Cartoon / Lively，本来就是配卡通角色的）
  - zh-CN-XiaoxiaoNeural 抬高音调、加快语速（更像"少女/萝莉"）
所以做几个不同的音调/语速组合，一次听完再挑。
"""
import asyncio
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TTS = ROOT / "tts"
AUD = ROOT / "tts" / "audition"
AUD.mkdir(parents=True, exist_ok=True)

LINE = "你好呀，我是大肥鱼1号，今天也来陪你聊天啦，有什么想说的都可以告诉我。"

CANDIDATES = [
    ("A", "zh-CN-XiaoyiNeural", "+0%", "+0Hz", "小艺 原声（官方标注卡通/活泼）"),
    ("B", "zh-CN-XiaoyiNeural", "+10%", "+30Hz", "小艺 升调加语速（萌）"),
    ("C", "zh-CN-XiaoxiaoNeural", "+12%", "+35Hz", "晓晓 升调（少女感）"),
    ("D", "zh-CN-XiaoxiaoNeural", "+18%", "+50Hz", "晓晓 大幅升调（更萝莉）"),
    ("E", "zh-CN-XiaoxiaoNeural", "+6%", "+20Hz", "晓晓 轻微升调（自然偏甜）"),
    ("F", "zh-CN-XiaoyiNeural", "+15%", "+45Hz", "小艺 大幅升调（最萌）"),
]


async def synth(text, voice, rate, pitch, out):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(out))


def main():
    parts = []
    for tag, voice, rate, pitch, desc in CANDIDATES:
        label = f"候选 {tag}"
        lp = AUD / f"label_{tag}.mp3"
        sp = AUD / f"voice_{tag}.mp3"
        # 标签用中性男声，方便分辨
        asyncio.run(synth(label, "zh-CN-YunyangNeural", "+0%", "+0Hz", lp))
        asyncio.run(synth(LINE, voice, rate, pitch, sp))
        print(f"{tag}: {voice} rate={rate} pitch={pitch}  ({desc})")
        parts += [lp, sp]

    # 转 wav 再拼接（mp3 直接拼容易有兼容问题）
    wavs = []
    for i, p in enumerate(parts):
        w = AUD / f"part_{i:02d}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(p),
                        "-ar", "44100", "-ac", "1", str(w)], check=True)
        wavs.append(w)

    lst = AUD / "list.txt"
    lst.write_text("".join(f"file '{w.as_posix()}'\n" for w in wavs), encoding="utf-8")
    out = AUD / "audition-all.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat",
                    "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], check=True)
    print("\n试听文件:", out, f"{out.stat().st_size/1024/1024:.1f} MB")

    # 顺便把每个候选单独存一份，方便之后直接用
    for tag, voice, rate, pitch, desc in CANDIDATES:
        print(f"  {tag} -> tts/audition/voice_{tag}.mp3")


if __name__ == "__main__":
    main()
