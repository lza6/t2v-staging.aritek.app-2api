# -*- coding: utf-8 -*-
"""AIVG v1.9.1 上游压测 — 基线 / 边界 / Sign 校验矩阵（低频, 不做高频轰炸）"""
import json
import time
import concurrent.futures
import urllib.request
import urllib.error

UPSTREAM = "https://t2v.aritek.app"
SIGN_B91 = "1f7644d2530896653e3635a7129b89dad538004"
SIGN_PLAY = "5f349d58ed069b1810d23b71c67293818784b57b"

def req(path, headers, method="GET", body=None, timeout=25):
    data = json.dumps(body).encode() if body is not None else None
    h = dict(headers)
    if data:
        h["Content-Type"] = "application/json; charset=UTF-8"
    r = urllib.request.Request(UPSTREAM + path, data=data, headers=h, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, round(time.time() - t0, 2), resp.read(300).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, round(time.time() - t0, 2), e.read(300).decode("utf-8", "replace")
    except Exception as e:
        return 0, round(time.time() - t0, 2), f"ERR {e}"

def H(sign=SIGN_B91, vc="91"):
    return {"Sign": sign, "versionCode": vc, "Ctry-Target": "others", "pt": "en",
            "Device-Id": "aabbccddeeff00112233445566778899", "User-Agent": "okhttp/4.9.3"}

def banner(t):
    print(f"\n{'='*20} {t} {'='*20}")

# ---------- 场景 1: 基线 ----------
banner("场景1 基线")
for name, path, hdr in [
    ("home v3 无Sign", "/api/v3/t2v/home?v=3", {"User-Agent": "okhttp/4.9.3"}),
    ("home v3 playSign", "/api/v3/t2v/home?v=3", H(SIGN_PLAY)),
    ("home v3 b91Sign", "/api/v3/t2v/home?v=3", H()),
    ("user/info b91Sign", "/api/v1/user/info", H()),
    ("check-limit 无auth", "/api/v1/user/check-limit?ad_type=t2v_prompt", H()),
    ("redeem/check 假码", "/api/v1/redeem/check", {**H(), "Redeem-Code": "TESTCODE123"}),
]:
    c, t, b = req(path, hdr)
    print(f"  [{c}] {t}s {name}: {b[:120]}")

# ---------- 场景 2: 边界值 ----------
banner("场景2 边界值")
for name, body in [
    ("空prompt", {}),
    ("超长prompt(10KB)", {"prompt": "a" * 10240}),
    ("空ids", {"ids": []}),
    ("不存在jobId", {"ids": ["NONEXISTENT123"]}),
]:
    c, t, b = req("/api/v1/generate/status", H(), "POST", body)
    print(f"  [{c}] {t}s status/{name}: {b[:120]}")

# ---------- 场景 3: Sign 校验矩阵 ----------
banner("场景3 Sign 矩阵 (home 端点)")
for name, hdr in [
    ("正确b91", H()),
    ("错误deadbeef", H("deadbeef")),
    ("大写HEX", H(SIGN_B91.upper())),
    ("play证书", H(SIGN_PLAY)),
    ("无Sign", {"User-Agent": "okhttp/4.9.3", "Device-Id": "x" * 32}),
]:
    c, t, b = req("/api/v3/t2v/home?v=3", hdr)
    print(f"  [{c}] {t}s {name}: {'PASS' if c == 200 else b[:100]}")

# ---------- 场景 4: 并发(基线 5 并发 home) ----------
banner("场景4 并发 5x home")
def one(i):
    return req("/api/v3/t2v/home?v=3", H())[0:2]
with concurrent.futures.ThreadPoolExecutor(5) as ex:
    results = list(ex.map(one, range(5)))
print("  codes:", [r[0] for r in results], "times:", [r[1] for r in results])

print("\n[压测完成] 结论: home/status 公开端点可用; 生成类端点需合法 JWT(user_token), "
      "user/info 有独立签名校验, token bootstrap 需动态抓包(模拟器+Frida)。")
