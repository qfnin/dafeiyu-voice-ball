"""悬浮球启动器：先探一次 Electron 能不能渲染，再决定用哪种外壳。

三种模式（自动挑，写进 launch.log）：
  1) electron-live    —— Electron 不透明窗 + 圆形窗口区域，页面跑实时绑定（能眨眼/口型/微晃）
  2) electron-static  —— 同上，但页面走静态合成（原图 + 闭眼/嘴型差分），WebGL 挂掉时用
  3) edge             —— 退回 Edge app 窗口外壳（ball.py，适合没有 Electron 或权限异常的机器）

为什么不用透明窗：实测这个会话里 Electron 的透明窗根本画不出内容（截图 100% 透明），
不透明窗能正常渲染，再配 SetWindowRgn 裁成正圆，观感一样是干净圆球。
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "shell"
APP = ROOT / "app"
LOG_PATH = ROOT / "logs" / "launch.log"
SHOT = ROOT / "logs" / "ball.png"
RUIC_DIR = Path(os.environ.get("RUIC_HOME") or (ROOT.parent / "RuiC-2D"))
PYTHON = RUIC_DIR / ".venv" / "Scripts" / "python.exe"
PYTHONW = PYTHON.with_name("pythonw.exe")
ELECTRON = SHELL / "node_modules" / "electron" / "dist" / "electron.exe"


def log(*parts):
    line = time.strftime("%H:%M:%S") + "  " + " ".join(str(p) for p in parts)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def clean_env():
    env = dict(os.environ)
    for key in list(env):
        if key == "ELECTRON_RUN_AS_NODE" or key.startswith("DSH_"):
            env.pop(key, None)
    tmp = ROOT / "cache" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env["TMP"] = str(tmp)
    env["TEMP"] = str(tmp)
    return env


def analyse(png=None):
    """返回 (空白占比, 肤色占比)；拿不到就 (None, None)"""
    png = png or SHOT
    if not png.exists():
        return None, None
    try:
        from PIL import Image
    except ImportError:
        return None, None
    img = Image.open(png).convert("RGBA").resize((64, 64))
    px = list(img.getdata())
    # 透明 或 接近纯白 都算「没画东西」——透明截图最容易骗过只看白色的判断
    blank = sum(1 for r, g, b, a in px if a < 20 or (r > 232 and g > 232 and b > 232)) / len(px)
    skin = sum(1 for r, g, b, a in px if a >= 20 and r > 195 and g > 160 and b > 145 and r >= b - 10) / len(px)
    return blank, skin


def electron_probe(static, opaque=False):
    if not ELECTRON.exists():
        return None, None
    SHOT.unlink(missing_ok=True)
    env = clean_env()
    env["BALL_SHOT"] = "1"
    if opaque:
        env["BALL_OPAQUE"] = "1"
    else:
        env.pop("BALL_OPAQUE", None)
    if static:
        env["BALL_STATIC"] = "1"
    else:
        env.pop("BALL_STATIC", None)
    log(f"Electron 探针（{'静态' if static else '实时'}{'/不透明' if opaque else '/透明'}）…")
    try:
        subprocess.run([str(ELECTRON), "--no-sandbox", str(SHELL)], env=env, cwd=str(SHELL),
                       timeout=70, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        log("探针超时")
    return analyse()


def start_electron(static, opaque=False):
    env = clean_env()
    env["BALL_SHOT"] = ""
    if opaque:
        env["BALL_OPAQUE"] = "1"
    if static:
        env["BALL_STATIC"] = "1"
    log(f"启动 Electron 外壳（{'静态' if static else '实时'}{'/不透明' if opaque else '/透明'}）")
    subprocess.Popen([str(ELECTRON), "--no-sandbox", str(SHELL)], env=env, cwd=str(SHELL),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_edge_shell():
    log("启动 Edge app 窗口外壳（ball.py）")
    subprocess.Popen([str(PYTHONW), str(APP / "ball.py")], cwd=str(ROOT), env=clean_env(),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def already_running():
    for port in (8797, 9333):
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
    return False


def main():
    log("=== 启动器开始 ===")
    if already_running():
        log("检测到已经有球在跑，不再重复启动")
        return
    # 透明窗优先：圆形靠页面自己画，边缘最干净；实测透明窗在这台机器上能正常渲染
    blank, skin = electron_probe(static=False, opaque=False)
    log(f"透明+实时探针：空白 {None if blank is None else format(blank, '.1%')} / 肤色 {None if skin is None else format(skin, '.2%')}")
    if skin is not None and skin > 0.004:
        start_electron(static=False, opaque=False)
        return
    blank2, skin2 = electron_probe(static=True, opaque=False)
    log(f"透明+静态探针：空白 {None if blank2 is None else format(blank2, '.1%')} / 肤色 {None if skin2 is None else format(skin2, '.2%')}")
    if blank2 is not None and blank2 < 0.5:
        start_electron(static=True, opaque=False)
        return
    # 透明窗画不出来再试不透明窗 + 圆形区域
    blank3, skin3 = electron_probe(static=True, opaque=True)
    log(f"不透明+静态探针：空白 {None if blank3 is None else format(blank3, '.1%')}")
    if blank3 is not None and blank3 < 0.5:
        start_electron(static=True, opaque=True)
        return
    start_edge_shell()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log("启动器崩溃：\n" + traceback.format_exc())
        raise
