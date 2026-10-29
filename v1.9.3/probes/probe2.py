"""AIVG v1.9.3 第二轮：完整 type 白名单 + 真实 t2v 出片 + 路由探测"""
import json
import time
import urllib.request
import urllib.error
import sys
sys.path.insert(0, r"D:\aivg193")
from probe import http, bootstrap


def main():
    st, b = http("GET", "/api/v1/user/check-limit?type=__probe__")
    print("[type 白名单]", st, b.decode(errors="replace"))

    dev, token, st, raw = bootstrap()
    print(f"[device] {dev} st={st}")

    # 真实 t2v：最小 body
    body = {"prompt": "a calm ocean wave at sunset, cinematic, 4k"}
    t0 = time.time()
    st, b = http("POST", "/api/v4/video/t2v", token, json.dumps(body), timeout=600)
    dt = time.time() - t0
    print(f"[t2v 最小body] st={st} {dt:.1f}s {b[:400].decode(errors='replace')}")

    st, b = http("GET", f"/api/v1/user/check-limit?type=t2v_prompt", token)
    print(f"[配额消耗] {st} {b.decode(errors='replace')}")

    # 路由探测：v5 / 新端点
    for p in ["/api/v5/video/t2v", "/api/v4/video/t2v_v2", "/api/v4/video/dance",
              "/api/v4/video/i2v/dance", "/api/v1/user/plan", "/api/v4/t2v/styles"]:
        st, b = http("POST" if "video" in p else "GET", p, token,
                     json.dumps({"prompt": "x"}) if "video" in p else None, timeout=30)
        print(f"[route {p}] st={st} {b[:140].decode(errors='replace')}")


if __name__ == "__main__":
    main()
