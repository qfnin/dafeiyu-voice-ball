# 大肥鱼语音球 (DaFeiYu Voice Ball)

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![Node.js](https://img.shields.io/badge/Node.js-20%2B-339933?logo=node.js&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)

> 一颗住在桌面右上的小圆球，点一下就能和住在里面的鲸鱼娘「大肥鱼1号」语音聊天。

大肥鱼语音球是一个**全本地运行**的 Windows 桌面语音伴侣：透明置顶悬浮球里渲染 [RuiC-2D](https://github.com/HRuiCcc/RuiC-2D) 的实时角色，按住说话 → 本地 Whisper 识别 → LLM 回答 → edge-tts 合成开口说话。角色会眨眼、摆尾、口型对齐。

所有数据（缓存、日志、模型、配置）都写在项目自己的目录里，**不占 C 盘、不上传任何语音**。

## 功能

- 🎈 **桌面悬浮球**：透明无边框置顶小窗（Electron），位置记忆、右键菜单、开机自启、双击从最小化恢复
- 🗣️ **语音对话**：麦克风拾音 → faster-whisper 本地识别（自动断句）→ LLM → edge-tts 合成，口型随音量驱动
- 🧠 **三种回答后端**，`config.json` 里 `llm_backend` 一键切换：
  | 后端 | 说明 | 需要什么 |
  |---|---|---|
  | `ollama` | 本地模型，稳且免费（默认） | 安装 [Ollama](https://ollama.com) 并 `ollama pull qwen2.5-coder:7b` |
  | `dsh` | 走本机 DeepSeek Harness 的额度 | 本机运行 dsh web（端口 3425） |
  | `deepseek` | DeepSeek 官方 API | 设置环境变量 `DEEPSEEK_API_KEY` |
- 🐋 **角色可换**：`project` 字段指向任意 RuiC-2D 工程，默认自带「大肥鱼1号」
- 🎭 **人设可改**：`persona/whale-system-prompt.txt` 直接编辑

## 架构

```
大肥鱼语音球.vbs (双击启动，防重复启动)
  └─ app/start.ps1
       ├─ app/voice_bridge.py   语音桥 :8798（faster-whisper 识别 + LLM 调度）
       └─ app/launch.py
            └─ shell/main.js    Electron 悬浮球窗口
                 ├─ RuiC-2D 服务 :8796 /pet.html?project=da-fei-yu-1（角色渲染）
                 ├─ 语音桥 :8798（录音/合成/对话状态）
                 └─ edge-tts（子进程合成 mp3，逐句播放）
```

## 快速开始

### 前置要求

- Windows 10/11
- [Node.js](https://nodejs.org) ≥ 20、[Python](https://www.python.org) ≥ 3.10、Git
- 约 2 GB 磁盘空间（RuiC-2D 仓库 + Electron + Whisper 模型）

### 安装

```powershell
git clone https://github.com/HRuiCcc/dafeiyu-voice-ball.git
cd dafeiyu-voice-ball
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

`setup.ps1` 会自动：克隆角色引擎 RuiC-2D 到仓库旁边 → 建 Python venv 装依赖 → 装 Electron → （可选）预下载 Whisper 模型。

### 启动

双击仓库根目录的 **`大肥鱼语音球.vbs`**。球出现在屏幕右上角：

- **点一下球上的麦克风按钮，说一句话**——说完自动断句识别，回答完自动回待机；再点一下说下一句
- **右键** 弹出菜单：置顶开关、开机自启、静态模式、退出
- 再次双击 `.vbs` 只会把球从最小化恢复，不会重复启动

### 使用 DeepSeek 官方 API（可选）

```powershell
# 设置环境变量（或在 系统属性 → 环境变量 里永久设置）
setx DEEPSEEK_API_KEY "sk-你的key"
```

然后把 `config.json`（首次启动前复制 `config.example.json`）里的 `"llm_backend"` 改成 `"deepseek"`。

## 配置说明

复制 `config.example.json` 为 `config.json` 后修改（球的位置等会被程序自动写回）：

| 字段 | 默认 | 说明 |
|---|---|---|
| `project` | `da-fei-yu-1` | RuiC-2D 角色工程名 |
| `diameter` | `360` | 球直径（px） |
| `voice` | `zh-CN-XiaoyiNeural` | edge-tts 音色，任意 [官方音色](https://speech.platform.bing.com/tts/editor) 名 |
| `rate` / `pitch` | `+10%` / `+30Hz` | 语速 / 音调 |
| `whisper` | `base` | 识别模型：`tiny`(0.3s) `base`(0.6s) `small`(2.3s) |
| `llm_backend` | `ollama` | `ollama` \| `dsh` \| `deepseek` |
| `model` | `qwen2.5-coder:7b` | 后端对应的模型名 |
| `input_device` | `null` | 麦克风设备号；`null` = 每次通话自动探测有信号的设备 |
| `silence_rms` | `35` | 说话音量门槛（环境噪声大就调高） |
| `topmost` | `true` | 球是否置顶 |
| `hardCircle` | `false` | 是否用系统圆形裁切硬边（默认靠页面透明圆，边缘更细腻） |

## 目录结构

```
dafeiyu-voice-ball/
├─ 大肥鱼语音球.vbs        双击启动
├─ config.example.json     配置模板（复制为 config.json）
├─ app/                    Python 语音链路（识别/LLM/合成调度 + 启动器）
│   ├─ voice_bridge.py     语音桥 HTTP 服务 :8798
│   ├─ voice_engine.py     核心引擎：录音断句、whisper、LLM 后端、合成
│   ├─ launch.py           拉起 Electron
│   ├─ start.ps1           顶层启动器
│   └─ selftest_*.py       开发期自测脚本（抓屏验收球/菜单/麦克风）
├─ shell/                  Electron 外壳（窗口/右键菜单/开机自启/TTS 子进程）
├─ persona/                大肥鱼1号的系统提示词与人设
├─ assets/                 球图标
├─ tts/                    合成音频输出 + 试音样本
├─ scripts/
│   ├─ setup.ps1           一键安装
│   └─ prepare-models.ps1  预下载 Whisper 模型
└─ cache/ logs/ models/    运行时产物（git 忽略）
```

## 常见问题

**Q: 首次语音对话没反应？**
第一次会下载 Whisper 模型（约 150MB，走 hf-mirror 镜像），等一会儿；或先跑 `scripts\prepare-models.ps1`。

**Q: 识别不到我说话？**
环境噪声大把 `silence_rms` 调高；还不行就跑 `python app\selftest_mic2.py` 逐个设备测真实 RMS，再把设备号写进 `input_device`。

**Q: 想让球停在别的位置？**
直接拖球，位置自动记忆（写回 `config.json`）。

**Q: 不想用 ollama，想用回 DeepSeek？**
见上文「使用 DeepSeek 官方 API」。

**Q: 为什么坚持全本地？**
麦克风音频、对话记录、Whisper 推理全部不出本机；只有 LLM 回答走你选择的后端 API。

## 致谢

- 角色与渲染引擎：[RuiC-2D](https://github.com/HRuiCcc/RuiC-2D)（同一作者的另一个项目）
- 语音识别：[faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- 语音合成：[edge-tts](https://github.com/rany2/edge-tts)

## 作者

**清风同学灬** · GitHub: [qfnin](https://github.com/qfnin)

## License

[MIT](LICENSE)
