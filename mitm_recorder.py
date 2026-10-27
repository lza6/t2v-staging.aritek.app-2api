# -*- coding: utf-8 -*-
"""MITM 记录代理：模拟器 app -> 本地 8912 -> 真实上游，落盘所有请求/响应头"""
import http.server, urllib.request, ssl, json, time, os, threading

UPSTREAM = "https://t2v-staging.aritek.app/"
LOG = open("D:/aivg188/capture_log.jsonl", "a", encoding="utf-8")
LOCK = threading.Lock()
CTX = ssl.create_default_context()

class Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a): pass

    def _proxy(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        hdrs = {k: v for k, v in self.headers.items() if k.lower() not in ("host",)}
        url = UPSTREAM.rstrip("/") + self.path
        req = urllib.request.Request(url, data=body, method=method, headers=hdrs or None)
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                code, resp, rhdr = r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            code, resp, rhdr = e.code, e.read(), dict(e.headers)
        except Exception as e:
            code, resp, rhdr = 502, str(e).encode(), {}
        with LOCK:
            LOG.write(json.dumps({
                "t": time.strftime("%H:%M:%S"), "method": method, "path": self.path,
                "req_headers": hdrs,
                "req_body": body.decode("utf-8", "replace")[:3000] if body else None,
                "status": code,
                "resp_body": resp.decode("utf-8", "replace")[:3000].encode() and resp.decode("utf-8", "replace")[:3000],
            }, ensure_ascii=False) + "\n"); LOG.flush()
        print(f"[{time.strftime('%H:%M:%S')}] {method} {self.path} -> {code}")
        self.send_response(code)
        self.send_header("Content-Type", rhdr.get("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def do_GET(self): self._proxy("GET")
    def do_POST(self): self._proxy("POST")

if __name__ == "__main__":
    print("MITM recorder on :8912 -> t2v-staging.aritek.app")
    http.server.ThreadingHTTPServer(("0.0.0.0", 8912), Proxy).serve_forever()
