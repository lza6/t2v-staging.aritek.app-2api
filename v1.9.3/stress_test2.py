"""
AIVG v1.9.3 第二轮压测（更深）
==============================
S1 bootstrap 并发 50（worker 25）        —— 号池签发天花板 / IP 限流边界
S2 t2v 并发 20（独立设备）                —— 更高并发下的成功率与延迟退化
S3 t2i 僵尸 job 概率（20 采样, 120s 上限） —— 统计 succeeded / 卡死
S4 i2i 真实上传链路（2 次）                —— multipart 字段与配额
S5 prompt 边界（4999 / 5000 / 5001）      —— 硬限位置
S6 跨 type 配额独立性（同一设备）           —— t2v/t2i/i2i/enhance 是否共享计数
输出：evidence/stress2_<ts>.json
"""
from __future__ import annotations

import json
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from aivg193 import AivgClient, AivgError, new_device_id  # noqa: E402

OUT = Path(__file__).parent / "evidence"
OUT.mkdir(exist_ok=True)


def pct(xs):
    if not xs:
        return {}
    s = sorted(xs)
    return {"p50": round(statistics.median(s), 2), "p90": round(s[int(len(s) * .9)], 2),
            "p99": round(s[min(len(s) - 1, int(len(s) * .99))], 2), "max": round(max(s), 2),
            "avg": round(statistics.mean(s), 2)}


def summarise(name, rows, wall, extra=None):
    ok = [r for r in rows if r.get("ok")]
    errs = {}
    for r in rows:
        if not r.get("ok"):
            k = str(r.get("err", "?"))[:90]
            errs[k] = errs.get(k, 0) + 1
    out = {"name": name, "n": len(rows), "ok": len(ok), "fail": len(rows) - len(ok),
           "success_rate": round(len(ok) / len(rows) * 100, 1), "wall_s": wall,
           "latency_ms": pct([r["ms"] for r in ok]), "errors": errs}
    if extra:
        out.update(extra)
    print(f"\n### {name}: {out['ok']}/{len(rows)} ({out['success_rate']}%) wall={wall}s")
    if ok:
        print(f"    延迟 {out['latency_ms']}")
    for k, v in errs.items():
        print(f"    FAIL x{v} {k}")
    if extra:
        print(f"    {extra}")
    return out


def s1_bootstrap(i):
    c = AivgClient(new_device_id())
    t0 = time.time()
    try:
        c.bootstrap()
        lim = c.check_limit("t2v")
        return {"i": i, "ok": True, "ms": round((time.time() - t0) * 1000), "limit": lim}
    except Exception as e:  # noqa: BLE001
        return {"i": i, "ok": False, "ms": round((time.time() - t0) * 1000), "err": e}


def s2_t2v(i):
    c = AivgClient(new_device_id())
    t0 = time.time()
    try:
        c.bootstrap()
        url = c.t2v(f"round2 sample {i}: {random.choice(['a glass whale in the desert', 'a monk sweeping cherry blossoms', 'a floating city above clouds', 'a candle lit library at midnight'])}, cinematic")
        return {"i": i, "ok": True, "ms": round((time.time() - t0) * 1000), "url": url}
    except Exception as e:  # noqa: BLE001
        return {"i": i, "ok": False, "ms": round((time.time() - t0) * 1000), "err": e}


def s3_t2i_zombie(i, deadline=120):
    c = AivgClient(new_device_id())
    t0 = time.time()
    rec = {"i": i}
    try:
        c.bootstrap()
        r = c._request("POST", "/api/v4/image/t2i", token=c.token,
                       json_body={"prompt": [f"zombie probe {i}: {random.random()} a paper sculpture of a fox"]},
                       timeout=60)
        job = r.json()["data"]["jobId"]
        rec["job"] = job
        while time.time() - t0 < deadline:
            time.sleep(3)
            rr = c._request("POST", "/api/v1/generate/status", json_body={"ids": [job]}, timeout=60)
            it = (rr.json().get("data") or [{}])[0]
            if it.get("url"):
                rec.update(ok=True, ms=round((time.time() - t0) * 1000), state="succeeded", url=it["url"])
                return rec
            if it.get("status") == "failed":
                rec.update(ok=False, ms=round((time.time() - t0) * 1000), state="failed", err="job failed")
                return rec
        rec.update(ok=False, ms=round((time.time() - t0) * 1000), state="stuck",
                   err=f"still processing after {deadline}s")
        return rec
    except Exception as e:  # noqa: BLE001
        rec.update(ok=False, ms=round((time.time() - t0) * 1000), state="error", err=e)
        return rec


def s4_i2i(png: bytes):
    c = AivgClient(new_device_id())
    t0 = time.time()
    try:
        c.bootstrap()
        url = c.i2i([("in.png", png)], code="")
        return {"ok": True, "ms": round((time.time() - t0) * 1000), "url": url,
                "device": c.device_id[:8]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "ms": round((time.time() - t0) * 1000), "err": e}


def s5_prompt_limits():
    rows = []
    for n in (4999, 5000, 5001):
        c = AivgClient(new_device_id())
        c.bootstrap()
        t0 = time.time()
        try:
            url = c.t2v("y" * n)
            rows.append({"len": n, "ok": True, "ms": round((time.time() - t0) * 1000), "url": url})
        except AivgError as e:
            rows.append({"len": n, "ok": False, "ms": round((time.time() - t0) * 1000),
                         "err": str(e), "code": e.code, "http": e.status})
        except Exception as e:  # noqa: BLE001
            rows.append({"len": n, "ok": False, "ms": round((time.time() - t0) * 1000), "err": e})
    for r in rows:
        print(f"    len={r['len']} ok={r['ok']} http={r.get('http')} code={r.get('code')} {r.get('err', '')}")
    return rows


def s6_cross_type(png: bytes):
    c = AivgClient(new_device_id())
    c.bootstrap()
    before = {k: c.check_limit(k) for k in ("t2v", "t2i", "i2i")}
    out = {"device": c.device_id, "before": before, "steps": []}
    for label, fn in [("t2v", lambda: c.t2v("cross type probe: a single feather falling in sunlight")),
                      ("t2i", lambda: c.t2i("cross type probe: an origami crane on a desk")),
                      ("i2i", lambda: c.i2i([("in.png", png)]))]:
        t0 = time.time()
        try:
            url = fn()
            out["steps"].append({"step": label, "ok": True, "ms": round((time.time() - t0) * 1000), "url": url})
        except Exception as e:  # noqa: BLE001
            out["steps"].append({"step": label, "ok": False, "ms": round((time.time() - t0) * 1000), "err": str(e)[:200]})
    out["after"] = {k: c.check_limit(k) for k in ("t2v", "t2i", "i2i")}
    for s in out["steps"]:
        print(f"    {s['step']:4s} ok={s['ok']} {s['ms']}ms {s.get('url') or s.get('err')}")
    print(f"    before={out['before']}")
    print(f"    after ={out['after']}")
    return out


def main():
    import requests
    ts = time.strftime("%Y%m%d-%H%M%S")
    ev = {"ts": ts, "round": 2, "upstream": "https://t2v.aritek.app", "runs": {}}

    # 先拿一张种子图给 i2i 用
    seed_png = requests.get("https://sora.aritek.app/generates/20261029/1793284944877_4e417a9a8b7d47b8.png",
                            headers={"User-Agent": "okhttp/4.9.3"}, timeout=120).content
    print(f"seed png {len(seed_png)} bytes")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=25) as ex:
        rows = list(ex.map(s1_bootstrap, range(50)))
    ev["runs"]["S1"] = {"summary": summarise("S1 bootstrap 并发 50", rows, round(time.time() - t0, 1)),
                        "rows": rows}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=20) as ex:
        rows = list(ex.map(s2_t2v, range(20)))
    ev["runs"]["S2"] = {"summary": summarise("S2 t2v 并发 20", rows, round(time.time() - t0, 1)),
                        "rows": rows}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=10) as ex:
        rows = list(ex.map(s3_t2i_zombie, range(20)))
    states = {}
    for r in rows:
        states[r.get("state")] = states.get(r.get("state"), 0) + 1
    ev["runs"]["S3"] = {"summary": summarise("S3 t2i 僵尸 job 采样 20", rows, round(time.time() - t0, 1),
                                             {"states": states}), "rows": rows}

    print("\n### S4 i2i 真实上传")
    i2i_rows = [s4_i2i(seed_png) for _ in range(2)]
    for r in i2i_rows:
        print(f"    ok={r['ok']} {r['ms']}ms {r.get('url') or r.get('err')}")
    ev["runs"]["S4"] = {"summary": {"name": "S4 i2i", "ok": sum(1 for r in i2i_rows if r["ok"]),
                                    "n": len(i2i_rows)}, "rows": i2i_rows}

    print("\n### S5 prompt 边界")
    ev["runs"]["S5"] = {"summary": {"name": "S5 prompt 边界"}, "rows": s5_prompt_limits()}

    print("\n### S6 跨 type 配额独立性")
    ev["runs"]["S6"] = s6_cross_type(seed_png)

    p = OUT / f"stress2_{ts}.json"
    p.write_text(json.dumps(ev, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n证据已写入 {p}")


if __name__ == "__main__":
    main()
