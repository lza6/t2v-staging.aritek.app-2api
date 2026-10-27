# -*- coding: utf-8 -*-
"""本地压测脚本：打 demo_server (8911)，不打上游。"""
import argparse, json, statistics, threading, time, urllib.request

BASE = "http://127.0.0.1:8911"
SIGN = "5f349d58ed069b1810d23b71c67293818784b57b"
HDR = {"Sign": SIGN, "versionCode": "88", "Content-Type": "application/json",
       "Authorization": "Bearer test-token", "Device-Id": "bench-device"}

def call(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=HDR)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read(); return r.status, (time.perf_counter() - t0) * 1000, None
    except urllib.error.HTTPError as e:
        e.read(); return e.code, (time.perf_counter() - t0) * 1000, None
    except Exception as e:
        return 0, (time.perf_counter() - t0) * 1000, str(e)

def worker(n, path, method, body, results):
    for _ in range(n):
        code, ms, err = call(method, path, body)
        results.append((code, ms, err))

def run(name, method, path, body, threads, total):
    results = []
    per = total // threads
    ts = [threading.Thread(target=worker, args=(per, path, method, body, results)) for _ in range(threads)]
    t0 = time.perf_counter()
    for t in ts: t.start()
    for t in ts: t.join()
    wall = (time.perf_counter() - t0) * 1000
    ok = [ms for c, ms, e in results if c == 200]
    errc = sum(1 for c, _, _ in results if c != 200)
    print(f"\n== {name}: {total} req / {threads} threads ==")
    print(f"  wall={wall:.0f}ms  throughput={total/(wall/1000):.1f} rps")
    if ok:
        print(f"  ok={len(ok)} err={errc}  p50={statistics.median(ok):.1f}ms  p95={sorted(ok)[int(len(ok)*0.95)]:.1f}ms  avg={statistics.mean(ok):.1f}ms")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--total", type=int, default=200)
    a = ap.parse_args()
    run("home", "GET", "/api/v2/t2v/home?v=1", None, a.threads, a.total)
    run("user-info", "GET", "/api/v1/user/info", None, a.threads, a.total)
    run("check-limit", "GET", "/api/v1/user/check-limit?type=video", None, a.threads, a.total)
    run("t2v-create", "POST", "/api/v3/video/t2v", {"prompt": "a cat flying", "versionCode": 88}, a.threads, max(a.total // 4, 20))
    run("moderation", "POST", "/api/v1/moderation/check-input", {"prompt": "sunset beach"}, a.threads, a.total)
    # 错误路径：错误 Sign 应被拒绝
    HDR["Sign"] = "deadbeef"
    code, ms, _ = call("GET", "/api/v1/user/info")
    print(f"\n== negative test: bad Sign -> HTTP {code} (期望 401) ==")
    HDR["Sign"] = SIGN
    _, ms, _ = call("POST", "/benchmark")
