"""
AIVG v1.9.3 本地 Demo 网关
==========================
把 aritek 的 t2v/t2i 协议包装成「OpenAI 兼容 + 简单 REST」本地服务，共用号池。

  GET  /                       demo 页面
  POST /t2v                    {"prompt": str, "aspect_ratio": "9:16|16:9|1:1", "ai_sound": 0|1}
  POST /t2i                    {"prompt": str}
  POST /v1/images/generations  OpenAI 图像协议
  POST /v1/chat/completions    OpenAI 对话协议（model=aivg-t2v / aivg-t2i，返回 [video](url) / [image](url)）
  GET  /health                 健康检查
  GET  /stats                  号池统计
"""
from __future__ import annotations

import json
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aivg193 import AivgError, DevicePool, PROMPT_MAX

PORT = 8916
HOST = "0.0.0.0"
HERE = Path(__file__).resolve().parent
POOL = DevicePool()
START_TS = time.time()


def _cors(self) -> None:
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Headers", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "aivg193-demo/1.0"

    def log_message(self, fmt, *args):  # 只保留错误
        if str(args[1] if len(args) > 1 else "") not in ("200", "204"):
            print(f"[{time.strftime('%H:%M:%S')}] {self.address_string()} {fmt % args}")

    # ---------- 工具 ----------
    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        _cors(self)
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            return {}

    def _err(self, e: Exception) -> None:
        if isinstance(e, AivgError):
            self._json(502, {"error": {"message": str(e), "code": e.code,
                                       "upstream_status": e.status, "body": e.body}})
        else:
            self._json(500, {"error": {"message": str(e), "trace": traceback.format_exc()[-800:]}})

    # ---------- 路由 ----------
    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            data = (HERE / "demo.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            _cors(self)
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/health":
            self._json(200, {"ok": True, "upstream": "t2v.aritek.app",
                             "version": "1.9.3", "uptime_s": round(time.time() - START_TS)})
            return
        if self.path == "/stats":
            self._json(200, POOL.snapshot())
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        body = self._body()
        try:
            if self.path == "/t2v":
                self._handle_t2v(body)
            elif self.path == "/t2i":
                self._handle_t2i(body)
            elif self.path == "/v1/images/generations":
                self._handle_images(body)
            elif self.path == "/v1/chat/completions":
                self._handle_chat(body)
            else:
                self._json(404, {"error": {"message": "not found"}})
        except Exception as e:  # noqa: BLE001
            self._err(e)

    # ---------- 业务 ----------
    def _prompt_of(self, body: dict) -> str:
        p = (body.get("prompt") or "").strip()
        if not p and isinstance(body.get("messages"), list):
            for m in reversed(body["messages"]):
                if m.get("role") == "user":
                    c = m.get("content")
                    if isinstance(c, str):
                        p = c.strip()
                    elif isinstance(c, list):
                        p = "".join(x.get("text", "") for x in c if isinstance(x, dict)).strip()
                    break
        if not p:
            raise AivgError("prompt required", code=-1)
        if len(p) > PROMPT_MAX:
            raise AivgError(f"prompt too long ({len(p)} > {PROMPT_MAX})", code=-6)
        return p

    def _handle_t2v(self, body: dict) -> None:
        prompt = self._prompt_of(body)
        d = POOL.acquire("t2v")
        t0 = time.time()
        url = d.client.t2v(prompt, body.get("aspect_ratio") or "", int(body.get("ai_sound") or 0))
        self._json(200, {"type": "video", "url": url, "device": d.device_id[:8],
                         "elapsed_ms": round((time.time() - t0) * 1000)})

    def _handle_t2i(self, body: dict) -> None:
        prompt = self._prompt_of(body)
        d = POOL.acquire("t2i")
        t0 = time.time()
        url = d.client.t2i(prompt)
        self._json(200, {"type": "image", "url": url, "device": d.device_id[:8],
                         "elapsed_ms": round((time.time() - t0) * 1000)})

    def _handle_images(self, body: dict) -> None:
        prompt = self._prompt_of(body)
        n = max(1, min(int(body.get("n") or 1), 3))
        d = POOL.acquire("t2i")
        data = []
        for _ in range(n):
            data.append({"url": d.client.t2i(prompt)})
        self._json(200, {"created": int(time.time()), "data": data})

    def _handle_chat(self, body: dict) -> None:
        prompt = self._prompt_of(body)
        model = body.get("model") or "aivg-t2v"
        is_video = "t2v" in model or "video" in model
        d = POOL.acquire("t2v" if is_video else "t2i")
        t0 = time.time()
        url = d.client.t2v(prompt) if is_video else d.client.t2i(prompt)
        kind = "video" if is_video else "image"
        created = int(time.time())
        self._json(200, {
            "id": f"chatcmpl-aivg-{created}",
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": f"[{kind}]({url})"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": len(prompt), "completion_tokens": 0, "total_tokens": len(prompt)},
            "device": d.device_id[:8],
            "elapsed_ms": round((time.time() - t0) * 1000),
        })


def main() -> None:
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    srv.daemon_threads = True
    print(f"AIVG v1.9.3 demo gateway → http://127.0.0.1:{PORT}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
