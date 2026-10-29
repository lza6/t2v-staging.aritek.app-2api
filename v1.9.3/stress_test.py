"""
AIVG v1.9.3 本地压测（第一轮）
=============================
场景：
  R1  t2v 并发 N（每请求全新 Device-Id）      —— 出片吞吐/延迟/限流
  R2  bootstrap 并发 N（号池签发压力）        —— 无限签发是否被 IP 限流
  R3  t2i 并发 N（异步 job + 轮询）           —— 图生链路稳定性
  R4  单设备配额打尽（同一 Device 连打）      —— 配额语义/错误码
输出：evidence/stress_<ts>.json + 控制台汇总
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from aivg193 import AivgClient, AivgError, new_device_id  # noqa: E402

OUT = Path(__file__).parent / "evidence"
OUT.mkdir(exist_ok=True)
PCT = lambda xs, p: (sorted(xs)[min(len(xs) - 1, int(len(xs) * p / 100))] if xs else 0)


def pct(xs):
    if not xs:
        return {}
    return {"p50": round(statistics.median(xs), 2), "p90": round(PCT(xs, 90), 2),
            "p99": round(PCT(xs, 99), 2), "max": round(max(xs), 2),
            "avg": round(statistics.mean(xs), 2)}


def one_t2v(i: int) -> dict:
    c = AivgClient(new_device_id())
    t0 = time.time()
    rec = {"i": i, "device": c.device_id[:8]}
    try:
        c.bootstrap()
        url = c.t2v(f"subject {i}: a colorful hot air balloon over a canyon at sunrise, cinematic")
        rec.update(ok=True, ms=round((time.time() - t0) * 1000), url=url)
    except Exception as e:  # noqa: BLE001
        rec.update(ok=False, ms=round((time.time() - t0) * 1000), err=str(e)[:220])
    return rec


def one_bootstrap(i: int) -> dict:
    c = AivgClient(new_device_id())
    t0 = time.time()
    try:
        tok = c.bootstrap()
        lim = c.check_limit("t2v")
        return {"i": i, "ok": True, "ms": round((time.time() - t0) * 1000),
                "ttl": round(c.token_exp - time.time()), "limit": lim}
    except Exception as e:  # noqa: BLE001
        return {"i": i, "ok": False, "ms": round((time.time() - t0) * 1000), "err": str(e)[:220]}


def one_t2i(i: int) -> dict:
    c = AivgClient(new_device_id())
    t0 = time.time()
    try:
        c.bootstrap()
        url = c.t2i(f"subject {i}: a cozy bookshop interior with warm light, digital painting")
        return {"i": i, "ok": True, "ms": round((time.time() - t0) * 1000), "url": url}
    except Exception as e:  # noqa: BLE001
        return {"i": i, "ok": False, "ms": round((time.time() - t0) * 1000), "err": str(e)[:220]}


def single_device_quota(n: int = 12) -> dict:
    c = AivgClient(new_device_id())
    c.bootstrap()
    rows = []
    for i in range(n):
        t0 = time.time()
        try:
            url = c.t2v(f"quota probe {i}: rainy neon street, cinematic")
            rows.append({"i": i, "ok": True, "ms": round((time.time() - t0) * 1000), "url": url})
        except AivgError as e:
            rows.append({"i": i, "ok": False, "ms": round((time.time() - t0) * 1000),
                         "err": str(e), "code": e.code, "http": e.status})
            if e.status in (402, 429) or e.code in (-21, -99):
                break
    return {"device": c.device_id, "rows": rows}


def run(name, fn, n, workers):
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(fn, range(n)))
    wall = round(time.time() - t0, 1)
    ok = [r for r in rows if r["ok"]]
    lat = [r["ms"] for r in ok]
    errs = {}
    for r in rows:
        if not r["ok"]:
            key = r.get("err", "?")[:80]
            errs[key] = errs.get(key, 0) + 1
    summary = {"name": name, "n": n, "workers": workers, "wall_s": wall,
               "ok": len(ok), "fail": len(rows) - len(ok),
               "success_rate": round(len(ok) / n * 100, 1),
               "latency_ms": pct(lat), "errors": errs}
    print(f"\n### {name}: {len(ok)}/{n} 成功 ({summary['success_rate']}%)  wall={wall}s")
    if lat:
        print(f"  延迟 {summary['latency_ms']}")
    for k, v in errs.items():
        print(f"  FAIL x{v} {k}")
    return summary, rows


def main():
    ts = time.strftime("%Y%m%d-%H%M%S")
    evidence = {"ts": ts, "upstream": "https://t2v.aritek.app", "version": "1.9.3",
                "sign": "68d6165b72a7f2d8d17b0dc6fe9691abdf77c583", "runs": []}

    s1, r1 = run("R1 t2v 并发 8（独立设备）", one_t2v, 8, 8)
    evidence["runs"].append({"summary": s1, "rows": r1})

    s2, r2 = run("R2 bootstrap 并发 30", one_bootstrap, 30, 15)
    evidence["runs"].append({"summary": s2, "rows": r2})

    s3, r3 = run("R3 t2i 并发 4（异步轮询）", one_t2i, 4, 4)
    evidence["runs"].append({"summary": s3, "rows": r3})

    print("\n### R4 单设备配额打尽（t2v，最多 12 次）")
    r4 = single_device_quota(12)
    for row in r4["rows"]:
        mark = "OK  " if row["ok"] else "FAIL"
        print(f"  {mark} #{row['i']:2d} {row['ms']:6d}ms {row.get('url') or row.get('err')}")
    evidence["runs"].append({"summary": {"name": "R4 单设备配额"}, "rows": r4["rows"],
                             "device": r4["device"]})

    p = OUT / f"stress_{ts}.json"
    p.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n证据已写入 {p}")


if __name__ == "__main__":
    main()
