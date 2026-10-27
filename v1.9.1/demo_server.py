# -*- coding: utf-8 -*-
"""
AI Video Generator (aritek) v1.9.1 b91 — 2API demo server (OpenAI 兼容) 【全链路打通版】
上游: https://t2v.aritek.app  (生产环境, v4 协议)

关键突破 (相对 1.8.8):
- Sign 头必须 = 68d6165b72a7f2d8d17b0dc6fe9691abdf77c583 (模拟器+Frida 实测 App 运行时值;
  非 APK 静态证书 SHA1 —— 服务端白名单校验)
- user/info 用该 Sign 免鉴权 → 自动签发 guest JWT (ttl 3600, device_id 任意伪造 → 无限号池)
- t2v 同步返回 MP4 URL; t2i 异步 jobId → 轮询 status 得 PNG
- token 过期自动重新 bootstrap

用法: python demo_server.py  → http://0.0.0.0:8903
"""
import json
import time
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "https://t2v.aritek.app"
SIGN = "68d6165b72a7f2d8d17b0dc6fe9691abdf77c583"  # 实测运行时 Sign (白名单值)
VERSION_CODE = "91"
PORT = 8903

JOBS = {}          # job_id -> {"type","prompt","status","url","ts"}
JOBS_LOCK = threading.Lock()
STATS = {"requests": 0, "errors": 0, "jobs_submitted": 0, "bootstraps": 0}

# 简单 token 缓存: device_id -> (jwt, exp_ts)
TOKENS = {}
TOKENS_LOCK = threading.Lock()

MODELS = [
    {"id": "aivg-t2v", "object": "model", "owned_by": "aritek"},
    {"id": "aivg-t2i", "object": "model", "owned_by": "aritek"},
]


def upstream(path, method="GET", body=None, extra_headers=None, timeout=60):
    headers = {
        "Sign": SIGN,
        "versionCode": VERSION_CODE,
        "Ctry-Target": "others",
        "pt": "",
        "User-Agent": "okhttp/4.9.3",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json; charset=UTF-8"
    req = urllib.request.Request(UPSTREAM + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, json.dumps({"error": str(e)})


def get_token(device_id):
    """取缓存 token, 过期则重新 bootstrap (user/info 免鉴权签发)"""
    now = time.time()
    with TOKENS_LOCK:
        tok = TOKENS.get(device_id)
        if tok and tok[1] > now + 120:  # 提前 2 分钟刷新
            return tok[0]
    code, body = upstream("/api/v1/user/info", extra_headers={"Device-Id": device_id})
    resp = json.loads(body)
    if code == 200 and resp.get("code") == 0:
        jwt = resp["data"]["token"]
        ttl = resp["data"].get("ttl", 3600)
        with TOKENS_LOCK:
            TOKENS[device_id] = (jwt, now + ttl)
        STATS["bootstraps"] += 1
        return jwt
    raise RuntimeError(f"bootstrap failed: {code} {body[:200]}")


def poll_jobs():
    """后台轮询异步任务 (t2i 等)"""
    while True:
        with JOBS_LOCK:
            pending = [(jid, j) for jid, j in JOBS.items() if j["status"] in ("queued", "processing")]
        for jid, job in pending:
            try:
                jwt = get_token(job["device_id"])
                code, body = upstream("/api/v1/generate/status", "POST", {"ids": [jid]},
                                      {"Authorization": f"Bearer {jwt}"})
                item = json.loads(body)["data"][0]
                with JOBS_LOCK:
                    JOBS[jid]["status"] = item.get("status", "unknown")
                    JOBS[jid]["url"] = item.get("url", "")
            except Exception:
                pass
        time.sleep(4)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        STATS["requests"] += 1
        if self.path == "/health":
            with JOBS_LOCK:
                jobs = {k: {kk: vv for kk, vv in v.items() if kk != "device_id"} for k, v in JOBS.items()}
            return self._send(200, {
                "ok": True, "upstream": UPSTREAM, "sign": SIGN[:12] + "…",
                "stats": STATS, "tokens_cached": len(TOKENS), "jobs": jobs,
            })
        if self.path == "/v1/models":
            return self._send(200, {"object": "list", "data": MODELS})
        if self.path.startswith("/v1/tasks/"):
            jid = self.path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(jid)
            if not job:
                return self._send(404, {"error": "job not found"})
            return self._send(200, {
                "id": jid, "status": job["status"], "url": job["url"] or None,
                "type": job["type"], "prompt": job["prompt"], "created": job["ts"],
            })
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        STATS["requests"] += 1
        try:
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            STATS["errors"] += 1
            return self._send(400, {"error": "invalid json"})

        prompt = str(payload.get("prompt", "")).strip()
        if self.path in ("/v1/images/generations", "/v1/videos/generations") and not prompt:
            STATS["errors"] += 1
            return self._send(400, {"error": "prompt required"})

        device_id = str(payload.get("device_id", "")).strip() or "aivg2api-default-0000000001"
        is_video = self.path == "/v1/videos/generations"

        if self.path in ("/v1/images/generations", "/v1/videos/generations"):
            try:
                jwt = get_token(device_id)
            except Exception as e:
                STATS["errors"] += 1
                return self._send(502, {"error": f"token bootstrap failed: {e}"})
            auth = {"Authorization": f"Bearer {jwt}"}
            path = "/api/v4/video/t2v" if is_video else "/api/v4/image/t2i"
            # t2v: prompt 为字符串 (同步返回 url); t2i: prompt 为字符串数组 (异步 jobId)
            body = {"prompt": prompt} if is_video else {"prompt": [prompt]}
            code, body_txt = upstream(path, "POST", body, auth)
            STATS["jobs_submitted"] += 1
            try:
                resp = json.loads(body_txt)
            except Exception:
                STATS["errors"] += 1
                return self._send(502, {"upstream_status": code, "raw": body_txt[:400]})
            if resp.get("code") != 0:
                STATS["errors"] += 1
                return self._send(502, {"upstream_status": code, "upstream": resp})
            data = resp.get("data", {})
            if is_video:
                # t2v 同步出片
                return self._send(200, {
                    "object": "list", "created": int(time.time()), "model": "aivg-t2v",
                    "data": [{"url": data.get("url", "")}],
                })
            # t2i 异步: 注册轮询
            jid = data.get("jobId", "")
            with JOBS_LOCK:
                JOBS[jid] = {"type": "t2i", "prompt": prompt, "status": "processing",
                             "url": "", "ts": int(time.time()), "device_id": device_id}
            return self._send(200, {
                "object": "list", "created": int(time.time()), "model": "aivg-t2i",
                "data": [{"task_id": jid, "status": "processing",
                          "poll": f"/v1/tasks/{jid}"}],
            })

        if self.path == "/v1/moderation":
            text = str(payload.get("input", ""))
            try:
                jwt = get_token(device_id)
            except Exception as e:
                return self._send(502, {"error": f"token bootstrap failed: {e}"})
            # check-input: @q Query 参数 (非 body)
            code, body_txt = upstream(f"/api/v1/moderation/check-input?text={urllib.request.quote(text)}",
                                      extra_headers={"Authorization": f"Bearer {jwt}"})
            return self._send(200 if code == 200 else 502, {"upstream_status": code, "raw": body_txt[:400]})

        if self.path == "/native/home":
            code, body_txt = upstream("/api/v3/t2v/home?v=3")
            return self._send(200 if code == 200 else 502, json.loads(body_txt))

        return self._send(404, {"error": "not found"})


if __name__ == "__main__":
    threading.Thread(target=poll_jobs, daemon=True).start()
    print(f"[aivg-2api v1.9.1] listening on 0.0.0.0:{PORT} -> {UPSTREAM} (Sign={SIGN[:12]}…, 全链路打通)")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
