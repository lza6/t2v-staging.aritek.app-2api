# -*- coding: utf-8 -*-
"""
AIVG (t2v-staging.aritek.app) 2API 桥接 — 已全链路实测打通 (2026-10-28)
用法:
  1. 模拟器/真机跑 app 一次, 导出 JWT (见 README) 到 TOKEN.txt
  2. OPENAI_TOKEN 兼容入口: POST /v1/chat/completions {"messages":[{"role":"user","content":"prompt"}]}
     -> 返回视频 URL (markdown)
  3. 原生入口: POST /t2v {"prompt":"..."} -> {"video_url":...}
JWT 有效期 ~1h (payload.exp), 过期后重新导出。
端口 8914
"""
import json, time, urllib.request, ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SIGN = "5f349d58ed069b1810d23b71c67293818784b57b"   # Google Play 证书 SHA1 (已验证)
UPSTREAM = "https://t2v-staging.aritek.app"
CTX = ssl.create_default_context()

def load_token():
    try:
        return open("D:/aivg188/TOKEN.txt").read().strip()
    except Exception:
        return ""

TOKEN = {"v": load_token(), "ts": time.time()}
DEV = {"id": "8c6cbf9371916bce"}

def headers():
    return {"Sign": SIGN, "versionCode": "88", "Ctry-Target": "others", "pt": "",
            "Device-Id": DEV["id"], "Authorization": "Bearer " + TOKEN["v"],
            "Content-Type": "application/json", "User-Agent": "okhttp/4.12.0"}

def upstream(method, path, body=None, raw=False):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(UPSTREAM + "/" + path.lstrip("/"), data=data, method=method, headers=headers())
    try:
        with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
            b = r.read()
            return r.status, b.decode("utf-8", "replace") if not raw else b
    except urllib.error.HTTPError as e:
        b = e.read()
        return e.code, b.decode("utf-8", "replace") if not raw else b

def gen_t2v(prompt, aspect="9:16", ai_sound=0):
    st, body = upstream("POST", "api/v3/video/t2v", {
        "prompt": prompt, "versionCode": 88, "deviceID": DEV["id"],
        "isPremium": 0, "ctry_target": "others", "used": [],
        "aspect_ratio": aspect, "ai_sound": ai_sound})
    try:
        j = json.loads(body)
    except Exception:
        return {"error": body, "status": st}
    if j.get("code") == 0 and j["data"].get("url"):
        return {"video_url": j["data"]["url"]}
    # 某些模型走 jobId 轮询
    job = (j.get("data") or {}).get("jobId")
    if job:
        for _ in range(60):
            time.sleep(5)
            st2, b2 = upstream("POST", "api/v1/generate/status", {"jobId": job})
            j2 = json.loads(b2)
            d = j2.get("data") or {}
            if d.get("status") == "done" and d.get("url"):
                return {"video_url": d["url"]}
            if d.get("status") in ("failed", "error"):
                return {"error": b2}
    return {"error": body, "status": st}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/health"):
            # JWT 剩余时间
            try:
                import base64
                p = TOKEN["v"].split(".")[1]
                payload = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
                left = round((payload["exp"] - time.time()) / 3600, 2)
                self._json({"ok": True, "token_hours_left": left})
            except Exception as e:
                self._json({"ok": False, "err": str(e)})
        else:
            self._json({"usage": "POST /v1/chat/completions | POST /t2v {prompt}"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n)) if n else {}
        except Exception:
            return self._json({"error": "bad json"}, 400)
        if not TOKEN["v"] or time.time() - TOKEN["ts"] > 1800:
            TOKEN["v"] = load_token(); TOKEN["ts"] = time.time()
        if not TOKEN["v"]:
            return self._json({"error": "no token, export from device first"}, 503)

        if self.path.startswith("/v1/chat/completions"):
            prompt = ""
            for m in body.get("messages", []):
                if m.get("role") == "user":
                    prompt = m.get("content", "")
            if not prompt:
                return self._json({"error": "empty prompt"}, 400)
            r = gen_t2v(prompt)
            if "video_url" in r:
                self._json({"id": "aivg-t2v", "object": "chat.completion", "model": "aivg-t2v",
                            "choices": [{"index": 0, "message": {"role": "assistant",
                            "content": f"[▶️ AI Video]({r['video_url']})"}, "finish_reason": "stop"}]})
            else:
                self._json(r, 502)
        elif self.path.startswith("/t2v"):
            r = gen_t2v(body.get("prompt", ""))
            self._json(r, 200 if "video_url" in r else 502)
        else:
            self._json({"error": "not found"}, 404)

if __name__ == "__main__":
    print("aivg-2api bridge on :8914 | token loaded:", bool(TOKEN["v"]))
    ThreadingHTTPServer(("0.0.0.0", 8914), Handler).serve_forever()
