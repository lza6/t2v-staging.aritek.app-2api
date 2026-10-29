"""AIVG v1.9.3 上游协议探针（第一轮：bootstrap / check-limit / t2v 变体）"""
import json
import secrets
import sys
import urllib.request
import urllib.error

BASE = "https://t2v.aritek.app"
SIGN = "68d6165b72a7f2d8d17b0dc6fe9691abdf77c583"
VERSION_CODE = "93"


def http(method, path, token=None, body=None, extra_headers=None, timeout=120):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=body.encode() if isinstance(body, str) else body)
    req.add_header("sign", SIGN)
    req.add_header("versionCode", VERSION_CODE)
    req.add_header("Ctry-Target", "others")
    req.add_header("pt", "")
    req.add_header("User-Agent", "okhttp/4.9.3")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (extra_headers or {}).items():
        req.add_header(k, v)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}".encode()


def bootstrap(device=None):
    device = device or secrets.token_hex(16)
    st, b = http("GET", "/api/v1/user/info", extra_headers={"Device-Id": device})
    if st != 200:
        return device, None, st, b[:200]
    j = json.loads(b)
    return device, j["data"]["token"], st, b[:120]


def main():
    dev, token, st, raw = bootstrap()
    print(f"[bootstrap] st={st} device={dev} token={token[:20] if token else None}...")
    if not token:
        print("  raw:", raw)
        return
    payload = token.split(".")[1]
    import base64
    payload += "=" * (-len(payload) % 4)
    print("  jwt:", base64.urlsafe_b64decode(payload).decode())

    # check-limit 各种 type
    for t in ["t2v_prompt", "t2v", "t2i", "i2i", "i2v", "video", "image"]:
        st, b = http("GET", f"/api/v1/user/check-limit?type={t}", token)
        print(f"[check-limit {t}] {st} {b[:200].decode(errors='replace')}")

    # home 目录（t2v 模板）
    for v in [4, 5]:
        st, b = http("GET", f"/api/v4/t2v/home?v={v}", token)
        print(f"[home v={v}] {st} len={len(b)} {b[:160].decode(errors='replace')}")

    # redeem
    st, b = http("GET", "/api/v1/redeem/check")
    print(f"[redeem/check 无码] {st} {b[:200].decode(errors='replace')}")


if __name__ == "__main__":
    main()
