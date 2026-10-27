# -*- coding: utf-8 -*-
"""
AI Video Generator 1.8.8 (aritek) 逆向 demo 服务器
- 复刻 t2v 协议：同款请求头校验 + 端点
- 模拟任务队列 (t2v/t2i) + 轮询
- 内置压测端点 /benchmark (只打本地，不碰上游)
端口 8911
"""
import json, time, uuid, threading, random, argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SIGN = "5f349d58ed069b1810d23b71c67293818784b57b"
VERSION_CODE = "88"
JOBS = {}          # job_id -> {"status":..., "url":..., "created":...}
STATS = {"requests": 0, "rejected": 0, "by_endpoint": {}}
STATS_LOCK = threading.Lock()

TEMPLATES = [
    {"id": 1, "name": "Cinematic Drone", "thumb": "https://cdn.example.com/t1.jpg", "type": "t2v"},
    {"id": 2, "name": "Anime Style",     "thumb": "https://cdn.example.com/t2.jpg", "type": "t2v"},
    {"id": 3, "name": "AI Hug / Action Figure", "thumb": "https://cdn.example.com/t3.jpg", "type": "i2v"},
]

def record(ep):
    with STATS_LOCK:
        STATS["requests"] += 1
        STATS["by_endpoint"][ep] = STATS["by_endpoint"].get(ep, 0) + 1

def fake_video_url(job_id):
    return f"https://cdn.example.com/videos/{job_id}.mp4"

class Handler(BaseHTTPRequestHandler):
    server_version = "aivg-demo/1.0"

    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {self.address_string()} {fmt % args}")

    # ---- 协议头校验（复刻 HeaderInterceptor 语义） ----
    def check_headers(self):
        h = self.headers
        if h.get("Sign") != SIGN:
            return "invalid Sign header"
        if h.get("versionCode") != VERSION_CODE:
            return "versionCode mismatch"
        return None

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            try:
                return json.loads(self.rfile.read(n))
            except Exception:
                return {}
        return {}

    # ---- 路由 ----
    def do_GET(self):
        err = self.check_headers()
        path = self.path.split("?")[0]
        record(path)
        if err:
            STATS["rejected"] += 1
            return self.send_json({"code": 401, "message": err}, 401)
        q = self.path
        if path == "/api/v2/t2v/home":
            v = q.split("v=")[-1] if "v=" in q else "0"
            return self.send_json({"code": 0, "message": "ok", "data": {
                "version": int(v or 0), "templates": TEMPLATES,
                "trending": [], "banners": []}})
        if path == "/api/v1/user/info":
            tok = self.headers.get("Authorization", "")
            return self.send_json({"code": 0, "data": {
                "token": tok.replace("Bearer ", ""), "premium": 0,
                "credits": 10, "device_id": self.headers.get("Device-Id", "")}})
        if path == "/api/v1/user/check-limit":
            return self.send_json({"code": 0, "data": {"limit": 10, "used": 2, "remain": 8}})
        if path == "/api/v1/redeem/check":
            if self.headers.get("Redeem-Code"):
                return self.send_json({"code": 0, "data": {"valid": True, "credits": 50}})
            return self.send_json({"code": 400, "message": "missing Redeem-Code"}, 400)
        if path == "/stats":
            return self.send_json(STATS)
        self.send_json({"code": 404, "message": "not found"}, 404)

    def do_POST(self):
        err = self.check_headers()
        path = self.path.split("?")[0]
        record(path)
        if err:
            STATS["rejected"] += 1
            return self.send_json({"code": 401, "message": err}, 401)
        body = self.read_body()

        if path == "/api/v3/video/t2v":
            prompt = body.get("prompt", "")
            if not prompt:
                return self.send_json({"code": 400, "message": "prompt required"}, 400)
            job = uuid.uuid4().hex[:16]
            JOBS[job] = {"status": "processing", "url": None, "prompt": prompt, "created": time.time()}
            # 模拟异步生成：3 秒后完成
            threading.Timer(3.0, lambda: JOBS.update({job: {**JOBS[job], "status": "done", "url": fake_video_url(job)}})).start()
            return self.send_json({"code": 0, "message": "ok", "data": {"url": "", "jobId": job}})

        if path == "/api/v3/image/t2i":
            prompts = body.get("prompt", [])
            return self.send_json({"code": 0, "data": {
                "url": f"https://cdn.example.com/img/{uuid.uuid4().hex[:10]}.jpg",
                "jobId": uuid.uuid4().hex[:16]}})

        if path == "/api/v1/generate/status":
            job = body.get("jobId", "")
            info = JOBS.get(job)
            if not info:
                return self.send_json({"code": 404, "message": "unknown jobId"}, 404)
            return self.send_json({"code": 0, "data": {"jobId": job, "status": info["status"], "url": info["url"]}})

        if path == "/api/v1/moderation/check-input":
            prompt = str(body.get("prompt", ""))
            nsfw = any(w in prompt.lower() for w in ("nsfw", "nude", "xxx"))
            return self.send_json({"code": 0, "data": {"isSafe": not nsfw, "reason": "nsfw" if nsfw else None}})

        if path == "/benchmark":
            return self.send_json({"ok": True, "stats": STATS, "jobs_active": len(JOBS)})

        self.send_json({"code": 404, "message": "not found"}, 404)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8911)
    a = ap.parse_args()
    print(f"aivg demo server on :{a.port}  (Sign={SIGN[:12]}...)")
    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()
