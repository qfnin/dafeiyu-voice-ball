"""语音对话引擎：像打电话一样的长通话

一次「接通」，之后自动循环：
  听（录音，检测到说话 + 静音断句）
    -> 识别（Whisper）
    -> 回答（Ollama）
    -> 说出来（edge-tts）并驱动嘴型
    -> 说完自动回到「听」，继续下一轮
点「挂断」才停止。

防自听：播放她自己的声音时暂停采集，播完再开，避免把她的声音当成用户输入。

对外接口（给 voice_bridge.py 用）：
  call_start()   接通（开始循环）
  call_stop()    挂断
  status()       状态
  speak_text()   纯合成（调试用）
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "voice.log"
TTS_DIR = ROOT / "tts"
REC_DIR = ROOT / "cache" / "rec"
MODELS = ROOT / "models"
for d in (TTS_DIR, REC_DIR, MODELS, ROOT / "logs"):
    d.mkdir(parents=True, exist_ok=True)

# 全部放 D 盘；国内直连 huggingface 会超时，走镜像
os.environ.setdefault("HF_HOME", str(MODELS / "hf"))
os.environ.setdefault("HF_HUB_CACHE", str(MODELS / "hf" / "hub"))
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

OLLAMA = "http://127.0.0.1:11434"
PERSONA_FILE = ROOT / "persona" / "whale-system-prompt.txt"
# 回答后端：ollama（本地，稳且免费）| dsh（DSH 代理，用你的 DSH 额度）| deepseek（官方 API）
LLM_BACKENDS = {
    "ollama": {
        "url": "http://127.0.0.1:11434/api/chat",
        "model": "qwen2.5-coder:7b",
    },
    "dsh": {
        "url": "http://127.0.0.1:3425/v1/chat/completions",
        "model": "auto/deepseek-v4.1-flash",
        "api": "openai",
    },
    "deepseek": {
        "url": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-chat",
        "api": "openai",
        "apiKeyEnv": "DEEPSEEK_API_KEY",
    },
}
DEFAULTS = {
    "llm_backend": "ollama",     # ollama=本地(稳/免费/0.2s)  dsh=DSH额度  deepseek=官方API
    "model": "qwen2.5-coder:7b",
    "voice": "zh-CN-XiaoyiNeural",
    "rate": "+10%",
    "pitch": "+30Hz",
    "whisper": "base",           # tiny=0.3s base=0.6s small=2.3s；base 准确度和速度的平衡点
    "whisper_dir": str(MODELS / "whisper"),
    "system": (
        "你叫大肥鱼1号，是个住在用户桌面上的小圆球，正在和他语音通话。"
        "说话要短、口语化、可爱一点，像真人聊天：一次最多两句话，不要用 markdown、不要列清单。"
    ),
    "max_reply_chars": 60,     # 短回答 = 合成快 = 响应快（语音场景不需要长篇）
    "silence_sec": 1.2,        # 说完后静音这么久才断句（0.7 太短，说话中间一停顿就被切断）
    "max_record_sec": 12,      # 单句最长 12 秒
    "min_speech_sec": 1.0,     # 少于 1 秒的声音不算一句话（过滤咳嗽、杂音）
    "silence_rms": 120,        # 说话门槛：35 太灵敏，环境噪声都被当成说话
    "input_device": 1,         # 实测「阵列麦克风 (AMD Audio Device)」才有声音
    "history_turns": 6,        # 记住最近几轮对话，聊天才连贯
}

state = {
    "on_call": False,          # 是否在通话中
    "phase": "idle",           # idle | listening | thinking | speaking
    "recording": False,
    "busy": False,
    "auto_stopped": False,
    "last_text": "",
    "last_reply": "",
    "turns": 0,
    "error": "",
}
_lock = threading.Lock()
_history: list[dict] = []      # [{role, content}]
_pending_audio: list[str] = [] # 待播放的音频（逐句追加）
_synth_pool = None             # 合成线程池
_synth_futures: list = []      # 本轮待取回的合成任务
_whisper = None
_loop_thread: threading.Thread | None = None
_stop_flag = threading.Event()
_single_running = False    # 单句模式（按一下说一句）正在进行


def log(*parts):
    line = time.strftime("%H:%M:%S") + "  " + " ".join(str(p) for p in parts)
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def cfg():
    c = dict(DEFAULTS)
    p = ROOT / "config.json"
    try:
        c.update(json.loads(p.read_text(encoding="utf-8-sig")))
    except Exception:
        pass
    # 人设优先用 persona 文件（方便直接改），没有才用配置里的
    try:
        if PERSONA_FILE.exists():
            text = PERSONA_FILE.read_text(encoding="utf-8").strip()
            if text:
                c["system"] = text
    except OSError:
        pass
    return c


def get_whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        c = cfg()
        d = Path(c["whisper_dir"])
        d.mkdir(parents=True, exist_ok=True)
        log("加载 Whisper:", c["whisper"])
        _whisper = WhisperModel(c["whisper"], device="cpu", compute_type="int8",
                                download_root=str(d))
        log("Whisper 就绪")
    return _whisper


# ---------------------------------------------------------------- 单句录音
def pick_input_device() -> int | None:
    """自动挑一个真的有信号的输入设备

    这台机器上麦克风设备时好时坏（同一个设备有时 RMS 0、有时 40+），
    所以每次通话前都探一遍，挑当前能收到声音的那个。
    """
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        return None

    c = cfg()
    fixed = c.get("input_device")
    if isinstance(fixed, int) and fixed >= 0:
        # 配置里指定了就先测它，有信号就用
        try:
            r = sd.rec(int(0.8 * 16000), samplerate=16000, channels=1,
                       dtype="int16", device=fixed, blocking=True)
            rms = float(np.sqrt(np.mean(r.astype(np.float64) ** 2)))
            if rms > 5:
                return fixed
            log(f"指定设备 {fixed} 当前 RMS={rms:.0f}，尝试自动挑选")
        except Exception as exc:
            log(f"指定设备 {fixed} 打不开: {exc}")

    # 逐个试，挑信号最强的
    best, best_rms = None, 0.0
    seen = set()
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0:
            continue
        key = d["name"][:30]
        if key in seen:
            continue
        seen.add(key)
        try:
            r = sd.rec(int(0.6 * 16000), samplerate=16000, channels=1,
                       dtype="int16", device=i, blocking=True)
            rms = float(np.sqrt(np.mean(r.astype(np.float64) ** 2)))
            if rms > best_rms:
                best, best_rms = i, rms
        except Exception:
            continue
    if best is not None and best_rms > 5:
        log(f"自动选择输入设备 {best}（RMS={best_rms:.0f}）")
        return best
    log(f"没有设备有明显信号（最好 {best}: RMS={best_rms:.0f}），仍用 {best}")
    return best


def _record_once(max_sec=None, silence_sec=None) -> bytes:
    """录一句话，返回 PCM bytes；没说话返回 b''

    关键：不反复开关设备（这台机器上麦克风每次重新打开就可能没信号），
    而是在同一次打开里先「探测」再「录音」。
    """
    import sounddevice as sd
    import numpy as np

    c = cfg()
    rate = 16000
    max_sec = max_sec or c["max_record_sec"]
    silence_sec = silence_sec or c["silence_sec"]
    threshold = c.get("silence_rms", 20)
    block_sec = 0.1
    block_frames = int(rate * block_sec)

    # 候选设备：配置指定的 + 所有能打开的
    candidates = []
    fixed = c.get("input_device")
    if isinstance(fixed, int) and fixed >= 0:
        candidates.append(fixed)
    seen = set()
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0:
            continue
        key = d["name"][:30]
        if key in seen or i in candidates:
            continue
        seen.add(key)
        candidates.append(i)

    for dev in candidates:
        try:
            chunks: list[bytes] = []
            silence = 0.0
            spoke = False
            peak = 0.0
            started = time.time()
            blocks = 0
            noise_samples: list[float] = []
            threshold_now = threshold
            state["recording"] = True
            with sd.RawInputStream(samplerate=rate, channels=1, dtype="int16",
                                   blocksize=block_frames, device=dev) as stream:
                while True:
                    if _stop_flag.is_set():
                        break
                    data, overflowed = stream.read(block_frames)
                    pcm = bytes(data)
                    chunks.append(pcm)
                    blocks += 1
                    arr = np.frombuffer(pcm, dtype="int16").astype(np.float64)
                    rms = float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0
                    peak = max(peak, rms)

                    # 前 1.5 秒当作环境底噪采样，据此动态设阈值
                    if blocks <= 15:
                        noise_samples.append(rms)
                        if blocks == 15 and noise_samples:
                            floor = sorted(noise_samples)[len(noise_samples) // 2]   # 中位数
                            threshold_now = max(threshold, floor * 3.5, floor + 80)
                            log(f"  设备{dev} 底噪 {floor:.0f} → 说话阈值 {threshold_now:.0f}")
                        if blocks % 20 == 0:
                            log(f"  [{dev}] 电平峰值 {peak:.0f}（阈值 {threshold_now:.0f}）spoke={spoke}")
                        continue

                    if blocks % 20 == 0:
                        log(f"  [{dev}] 电平峰值 {peak:.0f}（阈值 {threshold_now:.0f}）spoke={spoke}")
                    if rms < threshold_now:
                        silence += block_sec
                    else:
                        silence = 0.0
                        spoke = True
                    if spoke and silence >= silence_sec:
                        break
                    if time.time() - started > max_sec:
                        break
            state["recording"] = False

            if spoke:
                dur = blocks * block_sec
                min_dur = c.get("min_speech_sec", 1.0)
                if dur < min_dur:
                    log(f"  设备 {dev} 只录到 {dur:.1f}s（<{min_dur}s），太短不算一句")
                    return b""
                log(f"  设备 {dev} 录到声音（峰值 {peak:.0f}，{dur:.1f}s）")
                return b"".join(chunks)
            log(f"  设备 {dev} 没信号（峰值 {peak:.0f}），换下一个")
        except Exception as exc:
            state["recording"] = False
            log(f"  设备 {dev} 打不开: {str(exc)[:60]}")
            continue

    return b""


def _save_wav(pcm: bytes, path: Path) -> Path:
    """存成 wav，做音量归一化 + 针对这台机器的降噪

    实测这台笔记本内置麦克风的主频干扰在 366~375Hz（嗡嗡声），
    人声频段能量只占 17%，所以先做带通 + 陷波，再归一化。
    """
    import numpy as np
    arr = np.frombuffer(pcm, dtype="int16").astype(np.float64)
    if arr.size == 0:
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"")
        return path

    rate = 16000
    # 1) 高通 80Hz：去低频嗡鸣
    arr = _highpass(arr, 80, rate)
    # 2) 陷波 370Hz：干掉这台机器的主频干扰（Q=8 窄带）
    arr = _notch(arr, 370, rate, q=8.0)
    arr = _notch(arr, 720, rate, q=8.0)   # 谐波
    # 3) 归一化
    peak = float(np.max(np.abs(arr))) or 0.0
    if peak > 0:
        gain = min(32767 * 0.9 / peak, 30.0)
        if gain > 1.05:
            arr = arr * gain
            log(f"  归一化 ×{gain:.1f}")

    out = np.clip(arr, -32768, 32767).astype("int16")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(out.tobytes())
    return path


def _highpass(x, cutoff, rate, order=2):
    """一阶高通（级联 order 次）"""
    import numpy as np
    rc = 1.0 / (2 * np.pi * cutoff)
    dt = 1.0 / rate
    alpha = rc / (rc + dt)
    y = x.copy()
    for _ in range(order):
        out = np.zeros_like(y)
        prev_in = y[0]
        prev_out = y[0]
        for i in range(len(y)):
            out[i] = alpha * (prev_out + y[i] - prev_in)
            prev_in = y[i]
            prev_out = out[i]
        y = out
    return y


def _notch(x, freq, rate, q=8.0):
    """二阶陷波滤波器（去单一频率干扰）"""
    import numpy as np
    w0 = 2 * np.pi * freq / rate
    alpha = np.sin(w0) / (2 * q)
    b0, b1, b2 = 1, -2 * np.cos(w0), 1
    a0, a1, a2 = 1 + alpha, -2 * np.cos(w0), 1 - alpha
    b = np.array([b0, b1, b2]) / a0
    a = np.array([1.0, a1 / a0, a2 / a0])
    return _lfilter(b, a, x)


def _lfilter(b, a, x):
    """一维 IIR 滤波（不依赖 scipy）"""
    import numpy as np
    n = len(x)
    y = np.zeros(n)
    for i in range(n):
        acc = b[0] * x[i]
        for j in range(1, len(b)):
            if i - j >= 0:
                acc += b[j] * x[i - j]
        for j in range(1, len(a)):
            if i - j >= 0:
                acc -= a[j] * y[i - j]
        y[i] = acc / a[0]
    return y


# ---------------------------------------------------------------- 识别 / 回答 / 合成
def transcribe(path: Path) -> str:
    model = get_whisper()
    t0 = time.time()
    # 关掉 vad_filter：实测这台机器录到的音频音量偏低，VAD 会把整段判成静音
    segments, info = model.transcribe(
        str(path), language="zh",
        beam_size=1,                    # 1 比 5 快一倍，中文短句够用
        vad_filter=False,
        condition_on_previous_text=False,
        no_speech_threshold=0.9,
        without_timestamps=True,        # 不要时间戳，省一点
        temperature=0.0,                # 不采样，直接贪心
    )
    text = "".join(s.text for s in segments).strip()
    log(f"  识别({time.time()-t0:.2f}s): {text!r}")
    return text


def ask_llm_stream(text: str, on_sentence=None) -> str:
    """流式问模型：一边生成一边把完整句子回调出去，能提前开始合成"""
    c = cfg()
    _history.append({"role": "user", "content": text})
    keep = max(2, int(c.get("history_turns", 6)) * 2)
    msgs = [{"role": "system", "content": c["system"]}] + _history[-keep:]

    backend = c.get("llm_backend", "ollama")
    spec = LLM_BACKENDS.get(backend, LLM_BACKENDS["ollama"])
    reply_parts: list[str] = []
    buffer = ""

    try:
        if spec.get("api") == "openai":
            body = json.dumps({
                "model": c.get("model") or spec["model"],
                "messages": msgs,
                "stream": True,
                "max_tokens": 200,
                "temperature": 0.8,
            }).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            key_env = spec.get("apiKeyEnv")
            if key_env:
                key = os.environ.get(key_env, "")
                if not key:
                    try:
                        import yaml
                        cred = Path(os.environ.get("DSH_HOME", Path.home() / ".dsh")) / ".credentials.yaml"
                        if cred.exists():
                            d = yaml.safe_load(cred.read_text(encoding="utf-8"))
                            key = (d.get("refs") or {}).get(key_env, "")
                    except Exception:
                        pass
                if key:
                    headers["Authorization"] = f"Bearer {key}"
            req = urllib.request.Request(spec["url"], data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        obj = json.loads(payload)
                        delta = ((obj.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                    except Exception:
                        continue
                    if not delta:
                        continue
                    reply_parts.append(delta)
                    buffer += delta
                    # 碰到句末标点就把这句交出去，让外面先合成
                    if any(p in buffer for p in "。！？!?\n"):
                        sent = buffer.strip()
                        buffer = ""
                        if sent and on_sentence:
                            on_sentence(sent)
        else:
            # Ollama 流式
            body = json.dumps({
                "model": c.get("model") or spec["model"],
                "messages": msgs,
                "stream": True,
                "options": {"temperature": 0.8, "num_predict": 200},
            }).encode("utf-8")
            req = urllib.request.Request(spec["url"], data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    delta = (obj.get("message") or {}).get("content") or ""
                    if not delta:
                        continue
                    reply_parts.append(delta)
                    buffer += delta
                    if any(p in buffer for p in "。！？!?\n"):
                        sent = buffer.strip()
                        buffer = ""
                        if sent and on_sentence:
                            on_sentence(sent)
    except Exception as exc:
        log(f"流式 LLM 失败({backend}): {exc}")
        # 回退到非流式
        return ask_llm(text)

    if buffer.strip() and on_sentence:
        on_sentence(buffer.strip())

    reply = "".join(reply_parts).strip()
    reply = reply.replace("**", "").replace("##", "").replace("*", "")
    if len(reply) > c["max_reply_chars"]:
        reply = reply[: c["max_reply_chars"]].rstrip() + "…"
    _history.append({"role": "assistant", "content": reply})
    return reply


def ask_llm(text: str) -> str:
    """非流式版本（兜底 / 测试用）"""
    c = cfg()
    _history.append({"role": "user", "content": text})
    keep = max(2, int(c.get("history_turns", 6)) * 2)
    msgs = [{"role": "system", "content": c["system"]}] + _history[-keep:]

    backend = c.get("llm_backend", "ollama")
    spec = LLM_BACKENDS.get(backend, LLM_BACKENDS["ollama"])
    reply = ""

    try:
        if spec.get("api") == "openai":
            # OpenAI 兼容接口（DSH 代理 / DeepSeek 官方）
            body = json.dumps({
                "model": c.get("model") or spec["model"],
                "messages": msgs,
                "stream": False,
                "max_tokens": 300,
                "temperature": 0.8,
            }).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            key_env = spec.get("apiKeyEnv")
            if key_env:
                key = os.environ.get(key_env, "")
                if not key:
                    # 回退：从 DSH 凭据文件里读
                    try:
                        import yaml
                        cred = Path(os.environ.get("DSH_HOME", Path.home() / ".dsh")) / ".credentials.yaml"
                        if cred.exists():
                            data = yaml.safe_load(cred.read_text(encoding="utf-8"))
                            key = (data.get("refs") or {}).get(key_env, "")
                    except Exception:
                        pass
                if key:
                    headers["Authorization"] = f"Bearer {key}"
            req = urllib.request.Request(spec["url"], data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            reply = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
        else:
            # Ollama
            body = json.dumps({
                "model": c.get("model") or spec["model"],
                "messages": msgs,
                "stream": False,
                "options": {"temperature": 0.8, "num_predict": 200},
            }).encode("utf-8")
            req = urllib.request.Request(spec["url"], data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            reply = (data.get("message") or {}).get("content", "").strip()
    except Exception as exc:
        log(f"LLM({backend}) 失败: {exc}")
        # 自动回退到本地 Ollama，保证通话不中断
        if backend != "ollama":
            log("回退到本地 Ollama")
            body = json.dumps({
                "model": "qwen2.5-coder:7b",
                "messages": msgs,
                "stream": False,
                "options": {"temperature": 0.8, "num_predict": 200},
            }).encode("utf-8")
            req = urllib.request.Request(LLM_BACKENDS["ollama"]["url"], data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            reply = (data.get("message") or {}).get("content", "").strip()

    reply = reply.replace("**", "").replace("##", "").replace("*", "")
    if len(reply) > c["max_reply_chars"]:
        reply = reply[: c["max_reply_chars"]].rstrip() + "…"
    _history.append({"role": "assistant", "content": reply})
    return reply


async def _synth_stream(text: str, out: Path) -> float:
    """流式合成：边收边写文件，返回耗时。edge-tts 支持 stream()，比 save() 稍快且首包更早。"""
    import edge_tts
    c = cfg()
    t0 = time.time()
    comm = edge_tts.Communicate(text, c["voice"], rate=c["rate"], pitch=c["pitch"])
    buf = bytearray()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            buf.extend(chunk["data"])
    out.write_bytes(bytes(buf))
    return time.time() - t0


async def _synth(text: str, out: Path):
    import edge_tts
    c = cfg()
    await edge_tts.Communicate(text, c["voice"], rate=c["rate"], pitch=c["pitch"]).save(str(out))


def speak_text(text: str) -> str:
    out = TTS_DIR / "reply.mp3"
    t0 = time.time()
    import hashlib
    key = hashlib.md5(f"{text}|{cfg()['voice']}|{cfg()['rate']}|{cfg()['pitch']}".encode()).hexdigest()[:16]
    cached = TTS_DIR / f"cache-{key}.mp3"
    if cached.exists():
        log(f"  命中缓存 ({len(text)} 字)")
        data = cached.read_bytes()
        return "data:audio/mpeg;base64," + base64.b64encode(data).decode("ascii")

    try:
        dt = asyncio.run(_synth_stream(text, out))
        log(f"  流式合成 {len(text)} 字 {dt:.2f}s")
    except Exception as exc:
        log("  流式失败，回退:", exc)
        asyncio.run(_synth(text, out))
        log(f"  合成 {len(text)} 字 {time.time()-t0:.2f}s")
    data = out.read_bytes()
    try:
        cached.write_bytes(data)
    except OSError:
        pass
    return "data:audio/mpeg;base64," + base64.b64encode(data).decode("ascii")


# ---------------------------------------------------------------- 通话循环
def split_sentences(text: str, max_len: int = 40) -> list[str]:
    """把回答切成小句，第一句先合成先播，用户不用等整段"""
    import re
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[。！？!?；;…])", text)
    out, buf = [], ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) <= max_len:
            buf += p
        else:
            if buf:
                out.append(buf)
            buf = p
    if buf:
        out.append(buf)
    return out or [text]


def speak_sentences(text: str) -> list[str]:
    """逐句合成，返回 data URL 列表（第一句合成完就能先播）"""
    urls = []
    for i, sent in enumerate(split_sentences(text)):
        try:
            t0 = time.time()
            url = speak_text(sent)
            log(f"  第{i+1}句 {len(sent)}字 {time.time()-t0:.2f}s")
            urls.append(url)
        except Exception as exc:
            log(f"  第{i+1}句合成失败: {exc}")
    return urls


def speak_sentences_parallel(text: str) -> list[str]:
    """多句并发合成：几句话同时发请求，总耗时接近最慢那一句，而不是累加"""
    sents = split_sentences(text)
    if not sents:
        return []
    if len(sents) == 1:
        return [speak_text(sents[0])]
    pool = get_synth_pool()
    futures = [pool.submit(speak_text, s) for s in sents]
    urls = []
    for i, f in enumerate(futures):
        try:
            urls.append(f.result(timeout=30))
        except Exception as exc:
            log(f"  第{i+1}句并发合成失败: {exc}")
    return urls


def _reply_to_pcm(pcm: bytes) -> bool:
    """识别一句 → 回答 → 合成 → 等播完。返回是否完成了一轮有效回答"""
    state["phase"] = "thinking"
    wav = _save_wav(pcm, REC_DIR / "turn.wav")
    try:
        text = transcribe(wav)
    except Exception as exc:
        log("识别失败:", exc)
        state["error"] = f"识别失败：{exc}"
        return False
    text = (text or "").strip()
    if not text:
        log("没听清")
        return False
    log(f"听到: {text}")
    state["last_text"] = text

    # 回答（流式：一边生成一边合成一边播，第一句不用等整段）
    try:
        state["phase"] = "speaking"
        played: list[str] = []
        first_audio_at = [None]

        def on_sentence(sent: str):
            if _stop_flag.is_set():
                return
            # 关键：模型还在生成下一句时，这一句已经在后台合成了
            fut = get_synth_pool().submit(speak_text, sent)
            _synth_futures.append(fut)
            played.append(sent)
            log(f"  [{(time.time()-t_round)*1000:.0f}ms] 提交合成: {sent[:18]}")

        t_round = time.time()
        reply = ask_llm_stream(text, on_sentence)
        if not reply:
            return False
        log(f"  [{(time.time()-t_round)*1000:.0f}ms] 模型完成: {reply[:30]}")
        state["last_reply"] = reply
        state["turns"] += 1

        # 按顺序取回合成结果（此时多半已经好了）
        state["phase"] = "speaking"
        total = 0.0
        for i, fut in enumerate(_synth_futures):
            if _stop_flag.is_set():
                break
            try:
                url = fut.result(timeout=30)
                with _lock:
                    _pending_audio.append(url)
                if i == 0:
                    log(f"  [{(time.time()-t_round)*1000:.0f}ms] 第一句音频就绪 ← 用户开始听到")
                total += 1.5
            except Exception as exc:
                log("  合成失败:", exc)
        _synth_futures.clear()
        # 等这些句子播完（期间不采集，避免自听）
        t0 = time.time()
        while time.time() - t0 < total and not _stop_flag.is_set():
            time.sleep(0.1)
        # 多等一会儿，等扬声器余音散掉，别把回音当成下一句
        time.sleep(0.6)
        return True
    except Exception as exc:
        log("回答/合成失败:", exc)
        state["error"] = str(exc)
        return False


def _call_loop():
    """一直转：听 -> 想 -> 说 -> 再听，直到挂断"""
    log("=== 通话开始 ===")
    _history.clear()
    state["turns"] = 0
    empty_rounds = 0
    # 通话一开始就在后台预热常用语气词，第一次说话时就能命中缓存
    threading.Thread(target=prewarm_tts, daemon=True).start()

    while not _stop_flag.is_set():
        # --- 听
        state["phase"] = "listening"
        state["auto_stopped"] = False
        pcm = _record_once()
        if _stop_flag.is_set():
            break
        if not pcm or len(pcm) < 16000 * 0.25:      # 少于 0.25 秒算没说话
            empty_rounds += 1
            if empty_rounds % 20 == 0:
                log(f"连续 {empty_rounds} 次没听到声音（检查麦克风是否被占用/静音）")
            state["phase"] = "listening"
            time.sleep(0.15)
            continue
        empty_rounds = 0
        state["auto_stopped"] = True
        # --- 想 + 说
        _reply_to_pcm(pcm)

    state["phase"] = "idle"
    state["on_call"] = False
    state["recording"] = False
    log("=== 通话结束 ===")


def call_start():
    global _loop_thread
    with _lock:
        if state["on_call"]:
            return {"ok": True, "already": True}
        _stop_flag.clear()
        state["on_call"] = True
        state["phase"] = "listening"
        state["error"] = ""
        _loop_thread = threading.Thread(target=_call_loop, daemon=True)
        _loop_thread.start()
    return {"ok": True}


def call_stop():
    _stop_flag.set()
    state["on_call"] = False
    state["recording"] = False
    state["phase"] = "idle"
    log("挂断")
    return {"ok": True}


def _single_loop():
    """单句模式：听一句 -> 答一句 -> 结束（回到待机，等下一次点击）"""
    global _single_running
    log("=== 单句模式开始 ===")
    try:
        state["phase"] = "listening"
        state["auto_stopped"] = False
        pcm = _record_once()
        if _stop_flag.is_set():
            return
        if not pcm or len(pcm) < 16000 * 0.25:
            log("单句模式：没听到声音，本轮结束")
            return
        state["auto_stopped"] = True
        # --- 想 + 说（答完本轮就结束）
        _reply_to_pcm(pcm)
    finally:
        with _lock:
            _single_running = False
        state["phase"] = "idle"
        state["on_call"] = False
        state["recording"] = False
        log("=== 单句结束 ===")


def ask_once():
    """按一下说一句：开始一轮「听一句答一句」，答完自动回到待机"""
    global _single_running, _loop_thread
    with _lock:
        if state["on_call"] or _single_running:
            log("单句模式：上一轮还没结束，忽略本次点击")
            return {"ok": False, "busy": True}
        _stop_flag.clear()
        state["on_call"] = True
        state["phase"] = "listening"
        state["error"] = ""
        _single_running = True
        _loop_thread = threading.Thread(target=_single_loop, daemon=True)
        _loop_thread.start()
    log("单句模式：已接受点击，开始听")
    return {"ok": True, "mode": "once"}


def status() -> dict:
    s = dict(state)
    s.pop("last_url", None)
    return s


def pop_reply() -> dict | None:
    """外壳轮询：有新音频就取走（逐句返回，不用等整段）"""
    with _lock:
        if not _pending_audio:
            return None
        url = _pending_audio.pop(0)
        return {"url": url, "reply": state.get("last_reply", ""), "text": state.get("last_text", "")}


def get_synth_pool():
    """合成线程池：让多句能并行合成，第一句不用等后面的"""
    global _synth_pool
    if _synth_pool is None:
        from concurrent.futures import ThreadPoolExecutor
        _synth_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="tts")
        log("合成线程池已创建")
    return _synth_pool


def prewarm_tts():
    """预热：把常用短句先合成好放进缓存，真说话时直接命中

    这些是鲸鱼娘最可能说的开场白/语气词，命中率不低。
    """
    phrases = [
        "嗯嗯", "好的呀", "唔…", "哼", "让我想想", "主人",
        "我在呢", "怎么啦", "嘻嘻", "哦", "唔，这样啊", "才不是呢",
        "主人好呀", "嗯，我在听", "真的吗", "好的好的",
    ]
    ok = 0
    for p in phrases:
        try:
            speak_text(p)
            ok += 1
        except Exception:
            pass
    log(f"TTS 预热完成 {ok}/{len(phrases)}")
    return ok


def warmup():
    try:
        get_whisper()
    except Exception as exc:
        log("预热失败:", exc)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "warmup"
    if cmd == "warmup":
        warmup()
        print(json.dumps(status(), ensure_ascii=False))
    elif cmd == "say":
        print(speak_text(sys.argv[2] if len(sys.argv) > 2 else "你好")[:60])
    elif cmd == "llm":
        print(ask_llm(sys.argv[2] if len(sys.argv) > 2 else "你好"))
    elif cmd == "call":
        call_start()
        try:
            while True:
                time.sleep(1)
                print(json.dumps(status(), ensure_ascii=False))
        except KeyboardInterrupt:
            call_stop()
