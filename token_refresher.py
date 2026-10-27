# -*- coding: utf-8 -*-
"""
token 自动续期守护：模拟器常驻 + 每小时点 Generate 刷新 JWT 落盘 TOKEN.txt
前置: 模拟器(-http-proxy)已启动、patched APK 已装、mitm 不需要
用法: python token_refresher.py   (后台常驻, bridge 会自动重载 TOKEN.txt)
"""
import subprocess, time, re, os, sys

ADB = r"D:\android-sdk\platform-tools\adb.exe"
PKG = "ai.video.generator.text.video"
DEV = "-s emulator-5554"
SP = f"/data/data/{PKG}/shared_prefs/SoliText2Video.xml"
REFRESH_MIN = 45  # JWT 1h 有效, 45min 刷一次

def adb(*args):
    return subprocess.run([ADB, DEV] + list(args), capture_output=True, text=True, timeout=60).stdout

def current_token():
    out = adb("shell", "cat", SP)
    m = re.search(r'user_token">([^<]+)', out)
    return m.group(1) if m else ""

def frozen_interlopers():
    # AIVG 广告 SDK 会 enable 并拉起这些导流包, 循环冻结
    for p in ("com.technosub.unlimitedaiimagen", "com.blackhole.hd1763494114",
              "art.dreamerai.android", "org.greatfire.gfvpn"):
        adb("shell", "pm", "disable-user", "--user", "0", p)

def tap_ui_sequence():
    # 主界面出现后: 白嫖弹窗 [不再显示]→[取消]→Generate
    subprocess.run([ADB, DEV, "shell", "input", "tap", "540", "1745"], capture_output=True)
    time.sleep(1)
    subprocess.run([ADB, DEV, "shell", "input", "tap", "358", "1580"], capture_output=True)
    time.sleep(3)
    # uiautomator 取 Generate 精确坐标
    adb("shell", "uiautomator", "dump", "/sdcard/gx.xml")
    subprocess.run([ADB, DEV, "pull", "/sdcard/gx.xml", "D:/aivg188/gx.xml"], capture_output=True)
    try:
        x = open("D:/aivg188/gx.xml", encoding="utf-8", errors="replace").read()
        m = re.search(r'text="Generate"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', x)
        if m:
            xy = ((int(m.group(1)) + int(m.group(3))) // 2, (int(m.group(2)) + int(m.group(4))) // 2)
            subprocess.run([ADB, DEV, "shell", "input", "tap", str(xy[0]), str(xy[1])], capture_output=True)
            return True
    except Exception:
        pass
    return False

def refresh_once():
    old = current_token()
    adb("shell", "am", "force-stop", PKG)
    time.sleep(2)
    frozen_interlopers()
    adb("shell", "am", "start", "-n", f"{PKG}/.ui.activity.SplashActivity")
    # 等 Generate 出现（最多 90s）
    ok = False
    for _ in range(18):
        time.sleep(10)
        if tap_ui_sequence():
            ok = True
            break
    time.sleep(20)  # 等 token 落盘
    new = current_token()
    if new and new != old:
        open("D:/aivg188/TOKEN.txt", "w").write(new)
        print(f"[{time.strftime('%H:%M:%S')}] token refreshed, len={len(new)}", flush=True)
        return True
    print(f"[{time.strftime('%H:%M:%S')}] refresh failed (ok={ok}, got={bool(new)})", flush=True)
    return False

if __name__ == "__main__":
    print("token refresher started", flush=True)
    while True:
        refresh_once()
        time.sleep(REFRESH_MIN * 60)
